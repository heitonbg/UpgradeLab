"""Refresh sourced prices without replacing hardware IDs or benchmark scores.

Run from backend: python -m scripts.refresh_prices
PassMark affiliate prices are foreign retail prices converted at the CBR rate.
Rows with '*' (last-seen / unavailable) and missing prices are excluded.
"""
import html
import json
import re
import sqlite3
import statistics
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

import requests
from sqlalchemy import select
from app.db.base import Base, SessionLocal, engine
from app.db.models import Hardware, HardwarePrice
from app.services.hardware_matching import model_key
from scripts.parser import CPU_PAGE, GPU_PAGE, fetch_mega_data, get_session

ROOT = Path(__file__).resolve().parents[1]


def upsert(db, hw_id, source, amount, market, url, observed, count=1):
    quote = db.get(HardwarePrice, (hw_id, source))
    if quote and quote.observed_at > observed:
        return
    if quote is None:
        quote = HardwarePrice(hardware_id=hw_id, source=source)
        db.add(quote)
    quote.price_rub = round(amount)
    quote.market = market
    quote.source_url = url
    quote.observed_at = observed
    quote.sample_count = count
    db.flush()


def usd_rate():
    response = requests.get("https://www.cbr.ru/scripts/XML_daily.asp", timeout=20)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    for currency in root.findall("Valute"):
        if currency.findtext("CharCode") == "USD":
            rate = float(currency.findtext("Value").replace(",", ".")) / int(currency.findtext("Nominal"))
            return rate, root.attrib["Date"]
    raise ValueError("USD not found in the CBR response")


def refresh_passmark(db, hardware, rate):
    counts, errors, metadata = {}, [], []
    for hw_type, page in (("CPU", CPU_PAGE), ("GPU", GPU_PAGE)):
        try:
            rows = fetch_mega_data(get_session(page), page)
            if hw_type == "CPU":
                sockets = {}
                for row in rows:
                    if str(row.get("cpuCount", "1")) != "1":
                        continue
                    value = re.sub(r"<[^>]+>", "", html.unescape(str(row.get("socket", "")))).strip().upper()
                    value = value.replace("FCLGA", "LGA").replace("LGA ", "LGA")
                    if value in ("UNKNOWN", "NA", "N/A", "NONE", "-") or not re.fullmatch(r"[A-Z0-9 +\-/]{2,20}", value):
                        value = None
                    sockets.setdefault(model_key(row.get("name", "")), set()).add(value)
                for item in hardware:
                    if item.type != "CPU":
                        continue
                    values = sockets.get(model_key(item.name), set())
                    item.socket = next(iter(values)) if len(values) == 1 else None
                    metadata.append({"type": "CPU", "name": item.name, "socket": item.socket})
                seed_path = ROOT / "seed_data.json"
                seed = json.loads(seed_path.read_text(encoding="utf-8"))
                by_name = {model_key(item.name): item.socket for item in hardware if item.type == "CPU"}
                for item in seed.get("cpus", []):
                    item["socket"] = by_name.get(model_key(item["name"]))
                seed_path.write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            lookup = {}
            for item in hardware:
                if item.type == hw_type:
                    lookup.setdefault(model_key(item.name), []).append(item)
            count = 0
            for row in rows:
                if hw_type == "CPU" and str(row.get("cpuCount", "1")) not in ("1", ""):
                    continue
                price = html.unescape(str(row.get("price", "")))
                if "*" in price or not re.fullmatch(r"\$?[\d,]+\.\d{2}", price.strip()):
                    continue
                matches = lookup.get(model_key(row.get("name", "")), [])
                if len(matches) != 1:
                    continue
                amount = float(price.replace("$", "").replace(",", "")) * rate
                if not 10 <= amount <= 10000000:
                    continue
                upsert(db, matches[0].id, "passmark", amount, "retail_us_converted", page, datetime.utcnow())
                count += 1
            counts[hw_type] = count
            db.commit()
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            db.rollback()
            errors.append(f"{hw_type}: {exc}")
    return counts, errors, metadata


def import_avito_snapshot(db, hardware):
    path = ROOT / "avito_prices.db"
    if not path.exists():
        return 0
    with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as snapshot:
        rows = snapshot.execute("SELECT title, price, last_updated, item_id FROM current_prices").fetchall()
    # A title must contain a complete model designation; generic service ads,
    # bundles, model families and ambiguous matches are not price observations.
    lookup = [(hw, model_key(hw.name)) for hw in hardware if hw.type in ("CPU", "GPU")]
    grouped = {}
    for title, price, updated, item_id in rows:
        if not title or not price or price < 300:
            continue
        if re.search(r"ремонт|скуп|куплю|обмен|комплект|сборк|компьютер|ноутбук|неисправ|нерабоч|разбор|запчаст|процессор[ыа]\b", title, re.I):
            continue
        observed = datetime.fromisoformat(updated)
        if datetime.utcnow() - observed > timedelta(days=30):
            continue
        key = model_key(title)
        candidates = [(hw, name) for hw, name in lookup if name and name in key]
        if not candidates:
            continue
        longest = max(len(name) for _, name in candidates)
        candidates = [(hw, name) for hw, name in candidates if len(name) == longest]
        if len(candidates) != 1:
            continue
        hw, model = candidates[0]
        # Do not match a base model to a Ti/Super/XT variant or an extended number.
        suffix = key.split(model, 1)[1]
        if suffix and (suffix[0].isdigit() or suffix.startswith(("ti", "super", "xt", "k", "f", "t", "s"))):
            continue
        grouped.setdefault(hw.id, []).append((price, observed, item_id))
    for hw_id, observations in grouped.items():
        upsert(db, hw_id, "avito_snapshot", statistics.median(p for p, _, _ in observations), "used_ru",
               "https://www.avito.ru/" + str(observations[0][2]), min(t for _, t, _ in observations), len(observations))
    db.commit()
    return len(grouped)


def main():
    Base.metadata.create_all(engine)
    report = {"updated_at": datetime.utcnow().isoformat(), "errors": []}
    cache_path = ROOT / "price_data.json"
    previous = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    metadata = previous.get("metadata", [])
    with SessionLocal() as db:
        hardware = list(db.scalars(select(Hardware)))
        report["avito_snapshot"] = import_avito_snapshot(db, hardware)
        try:
            rate, rate_date = usd_rate()
            report["usd_rub"] = rate
            report["exchange_rate_date"] = rate_date
            counts, errors, refreshed_metadata = refresh_passmark(db, hardware, rate)
            if refreshed_metadata:
                metadata = refreshed_metadata
            report["passmark"] = counts
            report["errors"].extend(errors)
        except (requests.RequestException, ValueError, ET.ParseError) as exc:
            report["errors"].append(f"CBR: {exc}")
        # A portable cache is committed with the source so a fresh installation
        # can use the same dated observations. Old quotes still expire normally.
        quotes = [{"type": db.get(Hardware, q.hardware_id).type, "name": db.get(Hardware, q.hardware_id).name,
                   "price_rub": q.price_rub, "source": q.source, "market": q.market, "source_url": q.source_url,
                   "observed_at": q.observed_at.isoformat(), "sample_count": q.sample_count}
                  for q in db.scalars(select(HardwarePrice))]
        cache_path.write_text(json.dumps({"report": report, "quotes": quotes, "metadata": metadata}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
