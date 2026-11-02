"""Run with: python tests/test_smoke.py (httpx required in the test environment)."""
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
import sqlite3
from unittest import SkipTest

if __name__ != '__main__':
    raise SkipTest('Run test_smoke.py in its own process to isolate the database and settings.')

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory() as directory:
    os.environ["DATABASE_URL"] = "sqlite:///" + (Path(directory) / "smoke.db").as_posix()
    # Exercise the additive migration against the previous listings schema.
    with sqlite3.connect(Path(directory) / "smoke.db") as legacy:
        legacy.execute("CREATE TABLE listings (id INTEGER PRIMARY KEY, title VARCHAR(200) NOT NULL, condition VARCHAR(20) NOT NULL, price VARCHAR(50) NOT NULL, contact VARCHAR(200) NOT NULL, description TEXT, created_at DATETIME NOT NULL)")
        legacy.execute("INSERT INTO listings VALUES (1, 'Legacy GPU', 'Б/У', '1000', '@legacy', NULL, '2026-10-20 00:00:00')")
    legacy.close()

    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.base import engine
    from app.db.base import SessionLocal
    from app.db.models import Hardware, HardwarePrice
    from sqlalchemy import delete
    from app.services.calculator import calculate
    from app.schemas.calculate import GameName, CalcMode

    upgrade = calculate(cpu_raw=1000, gpu_raw=2000, game=GameName.CS2,
                        mode=CalcMode.MODE_1080P_LOW, cpu_socket="AM4", budget=3000,
                        all_cpus=[{"name": "Несовместимый", "raw_score": 10000, "avg_price": 1000, "socket": "AM5"},
                                  {"name": "Подходящий", "raw_score": 2000, "avg_price": 2000, "socket": "AM4"}],
                        all_gpus=[])
    assert upgrade.upgrade_component.startswith("Подходящий")
    assert upgrade.within_budget and upgrade.upgraded_fps > upgrade.current_fps
    no_budget = calculate(cpu_raw=1000, gpu_raw=2000, game=GameName.CS2, mode=CalcMode.MODE_1080P_LOW,
                          budget=0, all_cpus=[{"name": "Upgrade", "raw_score": 2000, "avg_price": 1000}])
    assert no_budget.upgrade_component is None
    assert no_budget.upgraded_fps == no_budget.current_fps

    minimal = calculate(cpu_raw=1000, gpu_raw=10000, game=GameName.CS2,
                        mode=CalcMode.MODE_1080P_LOW, cpu_socket="AM4", budget=10000, target_fps=60,
                        all_cpus=[{"id": 1, "name": "Cheap", "raw_score": 5000, "avg_price": 2000, "socket": "AM4"},
                                  {"id": 2, "name": "Expensive", "raw_score": 8000, "avg_price": 8000, "socket": "AM4"}])
    assert minimal.upgrade_id == 1 and minimal.upgraded_fps >= 60
    already = calculate(cpu_raw=10000, gpu_raw=10000, game=GameName.CS2, mode=CalcMode.MODE_1080P_LOW,
                        cpu_socket="AM4", budget=10000, target_fps=60,
                        all_cpus=[{"name": "Unnecessary", "raw_score": 20000, "avg_price": 1000, "socket": "AM4"}])
    assert already.upgrade_component is None and already.upgraded_fps == already.current_fps

    with TestClient(app) as client:
        assert client.get("/api/listings").json()[0]["listing_type"] == "sale"
        assert client.get("/api/listings").json()[0]["title"] == "Legacy GPU"
        assert client.get("/api/auth/discord/start", follow_redirects=False).status_code == 404
        hardware = client.get("/api/hardware")
        assert hardware.status_code == 200, hardware.text
        cpus = [h for h in hardware.json() if h["type"] == "CPU"]
        gpus = [h for h in hardware.json() if h["type"] == "GPU"]
        assert cpus and gpus
        assert next(h for h in cpus if h["name"] == "AMD FX-6100 Six-Core")["socket"] == "AM3+"
        assert next(h for h in cpus if h["name"] == "AMD Ryzen 5 5600X")["socket"] == "AM4"
        assert all(h["avg_price"] is None or h["price_source"] for h in hardware.json())
        detected_cpu = client.post("/api/detect-cpu", json={"cpu_name": "AMD FX(tm)-6100 Six-Core Processor"})
        assert detected_cpu.status_code == 200 and detected_cpu.json()["cpu_id"], detected_cpu.text
        assert client.post("/api/detect-cpu", json={"benchmark_time_ms": 100, "cpu_cores": 6}).json()["cpu_id"] is None
        payload = {"cpu_id": cpus[-1]["id"], "gpu_id": gpus[-1]["id"],
                   "game": "CS2", "mode": "1080p_low", "budget": 20000}

        calc = client.post("/api/calculate", json=payload)
        assert calc.status_code == 200, calc.text
        assert calc.json()["upgraded_fps"] >= calc.json()["current_fps"]
        unknown_ram = client.post("/api/calculate", json={**payload, "ram_manual": {"capacity_gb": 8, "type": "DDR3", "channels": None}})
        assert unknown_ram.status_code == 200, unknown_ram.text
        assert client.post("/api/calculate", json={**payload, "ram_id": cpus[0]["id"]}).status_code == 400
        assert client.post("/api/listings", json={"title": "Test GPU", "condition": "Б/У", "price": "1000", "contact": "@test"}).status_code == 401

        registered = client.post("/api/auth/register", json={"name": "Тест", "email": "test@example.com", "password": "longpassword"})
        assert registered.status_code == 201, registered.text
        assert client.get("/api/auth/me").json()["email"] == "test@example.com"
        assert client.post("/api/auth/register", json={"name": "Тест", "email": "test@example.com", "password": "longpassword"}).status_code == 409
        assert client.post("/api/auth/login", json={"email": "test@example.com", "password": "wrongpassword"}).status_code == 401
        assert client.post("/api/builds", json=payload, headers={"Origin": "https://untrusted.example"}).status_code == 403
        assert client.post("/api/builds", json=payload, headers={"Origin": "http://localhost:5173"}).status_code == 201

        build = client.post("/api/builds", json=payload)
        assert build.status_code == 201, build.text
        assert len(client.get("/api/builds").json()) == 2
        lot = {"title": "Test GPU", "condition": "Б/У", "price": "1000", "contact": "@test"}
        assert client.get("/api/auth/discord/start").status_code == 404
        assert client.post("/api/listings", json={**lot, "listing_type": "exchange"}).status_code == 422
        assert client.post("/api/listings", json={**lot, "photo_url": "javascript:alert(1)"}).status_code == 422
        exchange = client.post("/api/listings", json={**lot, "listing_type": "exchange", "price": "Обмен", "exchange_for": "Настройка ПК", "photo_url": "https://example.com/gpu.jpg"})
        assert exchange.status_code == 201, exchange.text
        assert exchange.json()["exchange_for"] == "Настройка ПК"
        assert client.delete(f"/api/listings/{exchange.json()['id']}").status_code == 204
        photo = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1sAAAAASUVORK5CYII="
        uploaded = client.post("/api/listings", json={**lot, "photo_url": photo})
        assert uploaded.status_code == 201 and uploaded.json()["photo_url"] == photo
        assert client.delete(f"/api/listings/{uploaded.json()['id']}").status_code == 204
        # Controlled prices keep build tests independent of real-world quote age.
        with SessionLocal() as db:
            db.execute(delete(HardwarePrice))
            fixtures = [("CPU", "Fixture cheap CPU", 4000, 2000, "AM4"),
                        ("CPU", "Fixture fast CPU", 8000, 8000, "AM4"),
                        ("GPU", "Fixture GPU", 5000, 3000, None),
                        ("GPU", "Fixture fast GPU", 10000, 9000, None)]
            fixture_ids = []
            for kind, name, score, price, socket in fixtures:
                hw = Hardware(type=kind, name=name, raw_score=score, normalized_score=50, socket=socket)
                db.add(hw);db.flush();fixture_ids.append(hw.id)
                db.add(HardwarePrice(hardware_id=hw.id, source="test", price_rub=price, market="retail_ru", source_url="https://example.com/quote", observed_at=datetime.utcnow()))
            db.commit()
        assembly = {"scenario": "build", "budget": 11000, "target_fps": 60, "game": "CS2", "mode": "1080p_low", "socket": "AM4", "ram_type": "DDR4", "ram_capacity_gb": 16,
                    **{key: {"name": "User specified part", "price": 1000} for key in ("motherboard", "memory", "storage", "psu", "case", "cooler")}}
        assembled = client.post("/api/assemble", json=assembly)
        assert assembled.status_code == 200, assembled.text
        assert assembled.json()["total_price"] <= assembly["budget"]
        assert len(assembled.json()["parts"]) == 8
        assert assembled.json()["target_reached"] == (assembled.json()["fps_outlook"]["minimum"] >= 60)
        assert assembled.json()["fps_outlook"]["minimum"] <= assembled.json()["fps"] <= assembled.json()["fps_outlook"]["maximum"]
        assert assembled.json()["total_price"] == 11000
        assert assembled.json()["parts"][0]["name"] == "Fixture cheap CPU"
        unattainable = client.post("/api/assemble", json={**assembly, "target_fps": 1000})
        assert unattainable.status_code == 200 and not unattainable.json()["target_reached"]
        assert client.post("/api/assemble", json={**assembly, "ram_type": "DDR5"}).status_code == 422
        assert client.post("/api/assemble", json={**assembly, "budget": 1}).status_code == 400
        saved_assembly = client.post("/api/builds", json=assembly)
        assert saved_assembly.status_code == 201, saved_assembly.text
        stored = next(b for b in client.get("/api/builds").json() if b["id"] == saved_assembly.json()["id"])
        assert stored["config"]["scenario"] == "build" and len(stored["result"]["parts"]) == 8
        assert client.delete(f"/api/builds/{saved_assembly.json()['id']}").status_code == 204
        with SessionLocal() as db:
            for quote in db.query(HardwarePrice).all():
                quote.observed_at = datetime.utcnow() - timedelta(days=31)
            db.commit()
        assert client.post("/api/assemble", json=assembly).status_code == 400
        listing = client.post("/api/listings", json={"title": "Test GPU", "condition": "Б/У", "price": "1000", "contact": "@test"})
        assert listing.status_code == 201, listing.text
        listing_id = listing.json()["id"]
        assert len(client.get("/api/my/listings").json()) == 1

        with TestClient(app) as stranger:
            assert stranger.get("/api/builds").status_code == 401
            stranger.post("/api/auth/register", json={"name": "Другой", "email": "other@example.com", "password": "longpassword"})
            assert stranger.get("/api/builds").json() == []
            assert stranger.delete(f"/api/builds/{build.json()['id']}").status_code == 404
            assert stranger.delete(f"/api/listings/{listing_id}").status_code == 404
        assert client.delete(f"/api/listings/{listing_id}").status_code == 204
        assert client.delete(f"/api/builds/{build.json()['id']}").status_code == 204
        assert client.post("/api/auth/logout").status_code == 204
        assert client.get("/api/auth/me").status_code == 401
        assert client.post("/api/auth/login", json={"email": "test@example.com", "password": "longpassword"}).status_code == 200
        assert client.get("/api/auth/me").status_code == 200
        old_cookie = client.cookies.get("upgrade_session")
        with TestClient(app, cookies={"upgrade_session": old_cookie}) as reopened:
            assert reopened.get("/api/auth/me").status_code == 200
            assert len(reopened.get("/api/builds").json()) == 1
        with TestClient(app) as another_browser:
            assert another_browser.get("/api/builds").status_code == 401
            login = another_browser.post("/api/auth/login", json={"email": "test@example.com", "password": "longpassword"})
            assert login.status_code == 200, login.text
            remote_builds = another_browser.get("/api/builds")
            assert remote_builds.headers["cache-control"] == "no-store"
            assert len(remote_builds.json()) == 1
        assert remote_builds.json()[0]["config"] == {**payload, "ram_id": None, "ram_manual": None, "ai_mode": "off", "sell_mode": "budget_only", "target_fps": 60, "price_sources": None, "refresh_avito_prices": False, "selected_upgrade_id": None, "expected_sale_price": None, "selected_platform": None}
        assert client.patch("/api/auth/profile", json={"name": "Новое имя"}).json()["name"] == "Новое имя"
        assert client.post("/api/auth/password", json={"current_password": "wrong", "new_password": "newpassword"}).status_code == 400
        assert client.post("/api/auth/password", json={"current_password": "longpassword", "new_password": "newpassword"}).status_code == 200
        with TestClient(app, cookies={"upgrade_session": old_cookie}) as revoked:
            assert revoked.get("/api/auth/me").status_code == 401
        assert client.post("/api/auth/login", json={"email": "test@example.com", "password": "longpassword"}).status_code == 401
        assert client.post("/api/auth/login", json={"email": "test@example.com", "password": "newpassword"}).status_code == 200

    engine.dispose()

print("Smoke test passed: minimal upgrade, full build, quote expiry, email auth, listing photos/exchange, ownership, legacy migration")
