"""Run with: python tests/test_smoke.py (httpx required in the test environment)."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory() as directory:
    os.environ["DATABASE_URL"] = "sqlite:///" + (Path(directory) / "smoke.db").as_posix()

    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.base import engine
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

    with TestClient(app) as client:
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
        listing = client.post("/api/listings", json={"title": "Test GPU", "condition": "Б/У", "price": "1000", "contact": "@test"})
        assert listing.status_code == 201, listing.text
        listing_id = listing.json()["id"]
        assert len(client.get("/api/my/listings").json()) == 1

        with TestClient(app) as stranger:
            stranger.post("/api/auth/register", json={"name": "Другой", "email": "other@example.com", "password": "longpassword"})
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
        assert client.patch("/api/auth/profile", json={"name": "Новое имя"}).json()["name"] == "Новое имя"
        assert client.post("/api/auth/password", json={"current_password": "wrong", "new_password": "newpassword"}).status_code == 400
        assert client.post("/api/auth/password", json={"current_password": "longpassword", "new_password": "newpassword"}).status_code == 200
        with TestClient(app, cookies={"upgrade_session": old_cookie}) as revoked:
            assert revoked.get("/api/auth/me").status_code == 401
        assert client.post("/api/auth/login", json={"email": "test@example.com", "password": "longpassword"}).status_code == 401
        assert client.post("/api/auth/login", json={"email": "test@example.com", "password": "newpassword"}).status_code == 200

    engine.dispose()

print("Smoke test passed: calculation, auth, saved builds, listing ownership")
