"""
Собирает десктопные процессоры и видеокарты с PassMark mega-страниц
через их же JSON-эндпоинт /data/ и сохраняет в seed_data.json.

Запуск из папки backend/:
    python -m scripts.parser
"""
import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_FILE = BASE_DIR / "seed_data.json"

CPU_PAGE = "https://www.cpubenchmark.net/CPU_mega_page.html"
GPU_PAGE = "https://www.videocardbenchmark.net/GPU_mega_page.html"

CPU_CATEGORIES = {"Desktop"}
GPU_CATEGORIES = {"Desktop"}
FILTER_CATEGORIES = True

# Слова, которых не должно быть в названии CPU
EXCLUDED_CPU_WORDS = {"threadripper", "epyc", "opteron"}

# Максимальный балл PassMark для Xeon (отсекаем современные серверные)
MAX_XEON_SCORE = 35000

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}


def clean_text(v) -> str:
    return "" if v is None else re.sub(r"\s+", " ", str(v)).strip()


def to_int(v) -> int | None:
    if v in (None, "", "NA", "N/A"):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    m = re.search(r"-?\d+(?:\.\d+)?", clean_text(v).replace(",", "").replace(" ", ""))
    return int(float(m.group())) if m else None


def get_session(page_url: str) -> requests.Session:
    s = requests.Session()
    h = dict(HEADERS)
    h["Referer"] = page_url
    s.headers.update(h)
    return s


def fetch_mega_data(session: requests.Session, page_url: str) -> list[dict]:
    domain = re.sub(r"^https?://", "", page_url).split("/")[0]
    print(f"  -> Запрос к {page_url} ...")
    page = session.get(page_url, timeout=30)
    page.raise_for_status()

    if "PHPSESSID" not in session.cookies:
        soup = BeautifulSoup(page.text, "html.parser")
        raise RuntimeError(
            f"Нет PHPSESSID со страницы {page_url} "
            f"(title: {clean_text(soup.title.string if soup.title else '')})"
        )

    data_url = f"https://{domain}/data/?_={int(time.time() * 1000)}"
    print(f"  -> Запрос к API данных: {data_url}")

    for attempt in range(3):
        r = session.get(data_url, timeout=(10, 120))
        if r.status_code in (403, 429):
            print(f"  -> Блокировка (код {r.status_code}). Ждем {2 * (attempt + 1)} сек...")
            time.sleep(2 * (attempt + 1))
            continue
        r.raise_for_status()
        break
    else:
        raise RuntimeError(f"PassMark отклонил запрос {data_url} (403/429)")

    try:
        payload = r.json()
    except json.JSONDecodeError as exc:
        raise RuntimeError("PassMark вернул не JSON — вероятно, изменился API.") from exc

    if isinstance(payload, list):
        return payload
    for key in ("data", "rows", "records", "items"):
        if isinstance(payload.get(key), list):
            return payload[key]
    raise RuntimeError(f"Не найден список записей. Ключи ответа: {list(payload.keys())}")


def normalize_cpu(raw: dict) -> dict | None:
    name = clean_text(raw.get("name"))
    score = to_int(raw.get("cpumark"))
    cat = clean_text(raw.get("cat")) or "Unknown"
    cores = to_int(raw.get("cores"))  # <-- Читаем ядра
    
    if not name or not score or score <= 0:
        return None
        
    if FILTER_CATEGORIES and cat not in CPU_CATEGORIES:
        return None
    
    name_lower = name.lower()
    
    # 1. Исключаем по ключевым словам
    if any(word in name_lower for word in EXCLUDED_CPU_WORDS):
        return None
        
    # 2. Умный фильтр для Xeon
    if "xeon" in name_lower:
        if score > MAX_XEON_SCORE:
            return None
            
    # 3. ИГРОВОЙ БОНУС ДЛЯ 3D V-CACHE (X3D)
    is_x3d = "x3d" in name_lower
    is_dual_x3d = is_x3d and ("9950x3d2" in name_lower or "dual" in name_lower)
    
    if is_dual_x3d:
        cef = 1.0
    elif is_x3d:
        cef = 1.15
        if score < 22000: 
            cef = 1.20
    else:
        cef = 1.0
        
    effective_score = int(score * cef)
            
    return {
        "name": name, 
        "score": effective_score, 
        "category": cat,
        "cores": cores  # <-- Добавляем ядра в JSON
    }


def normalize_gpu(raw: dict) -> dict | None:
    name = clean_text(raw.get("name"))
    score = to_int(raw.get("g3d"))
    cat = clean_text(raw.get("cat")) or "Unknown"
    
    if not name or not score or score <= 0:
        return None
        
    if FILTER_CATEGORIES and cat not in GPU_CATEGORIES:
        return None
        
    return {"name": name, "score": score, "category": cat}


def deduplicate(items: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for it in items:
        key = it["name"].lower()
        if key not in best or it["score"] > best[key]["score"]:
            best[key] = it
    return sorted(best.values(), key=lambda x: x["score"], reverse=True)


def parse_passmark() -> dict:
    cpu_session = get_session(CPU_PAGE)
    gpu_session = get_session(GPU_PAGE)

    print("1/2. Загрузка процессоров (CPU)...")
    cpu_raw = fetch_mega_data(cpu_session, CPU_PAGE)
    print(f"  -> Получено сырых записей: {len(cpu_raw)}")
    cpus = deduplicate([x for x in map(normalize_cpu, cpu_raw) if x])
    print(f"  -> Оставлено после фильтрации: {len(cpus)}")

    print("\n2/2. Загрузка видеокарт (GPU)...")
    gpu_raw = fetch_mega_data(gpu_session, GPU_PAGE)
    print(f"  -> Получено сырых записей: {len(gpu_raw)}")
    gpus = deduplicate([x for x in map(normalize_gpu, gpu_raw) if x])
    print(f"  -> Оставлено после фильтрации: {len(gpus)}")

    return {"cpus": cpus, "gpus": gpus}


def main() -> None:
    print("Начинаем парсинг PassMark (Desktop + старые Xeon + буст X3D)...")
    data = parse_passmark()
    
    if not data["cpus"] and not data["gpus"]:
        raise SystemExit("Не получено ни одной записи — проверьте доступ к PassMark.")

    OUTPUT_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    
    print(f"\nУспех! Данные сохранены в {OUTPUT_FILE}")
    print(f"Итог: CPU={len(data['cpus'])}, GPU={len(data['gpus'])}")


if __name__ == "__main__":
    main()