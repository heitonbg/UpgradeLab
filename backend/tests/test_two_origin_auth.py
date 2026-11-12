"""Two-origin production cookie and CORS contract without live network."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.account import router
from app.api.deps import get_db
from app.core.config import settings
from app.db.models import Base

FRONTEND = "https://frontendupgradelab-iwrawww.waw0.amvera.tech"
BACKEND = "https://backendupgradelab-iwrawww.waw0.amvera.tech"


class TwoOriginAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = create_engine("sqlite:///" + str(Path(self.temp.name) / "auth.db"))
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        for key, value in (
            ("cookie_secure", True), ("cookie_samesite", "none"),
            ("cors_origins", FRONTEND), ("frontend_url", FRONTEND),
            ("backend_url", BACKEND),
        ):
            changing = patch.object(settings, key, value)
            changing.start()
            self.addCleanup(changing.stop)
        app = FastAPI()
        app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins_list,
                           allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
        app.include_router(router)

        def isolated_db():
            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_db] = isolated_db
        self.client = TestClient(app, base_url=BACKEND)
        self.addCleanup(self.client.close)

    def test_production_defaults_and_fail_closed_configuration(self):
        from app.core.config import Settings
        with patch.dict("os.environ", {"AMVERA": "1"}, clear=True):
            config = Settings(_env_file=None)
            self.assertEqual(config.cors_origins_list, [FRONTEND])
            self.assertEqual(config.cookie_samesite, "none")
            self.assertTrue(config.cookie_secure)
            with patch.dict("os.environ", {"CORS_ORIGINS": "https://attacker.example"}):
                with self.assertRaises(ValueError):
                    Settings(_env_file=None)
            with patch.dict("os.environ", {"COOKIE_SECURE": "false"}):
                with self.assertRaises(ValueError):
                    Settings(_env_file=None)
    def test_cross_origin_login_cookie_and_session(self):
        response = self.client.post("/api/auth/register", json={
            "name": "Demo", "email": "demo@example.test",
            "password": "Safe-local-test-2026!",
        }, headers={"Origin": FRONTEND})
        self.assertEqual(response.status_code, 201, response.text)
        cookie = response.headers["set-cookie"].lower()
        for flag in ("httponly", "secure", "samesite=none"):
            self.assertIn(flag, cookie)
        self.assertEqual(response.headers["access-control-allow-origin"], FRONTEND)
        self.assertEqual(response.headers["access-control-allow-credentials"], "true")
        self.assertEqual(self.client.get("/api/auth/me", headers={"Origin": FRONTEND}).status_code, 200)
        self.assertEqual(self.client.patch("/api/auth/profile", json={"name": "Demo Two"},
                                           headers={"Origin": FRONTEND}).status_code, 200)
        logout = self.client.post("/api/auth/logout", headers={"Origin": FRONTEND})
        self.assertEqual(logout.status_code, 204)
        self.assertIn("samesite=none", logout.headers["set-cookie"].lower())
        self.assertIn("secure", logout.headers["set-cookie"].lower())
        self.assertEqual(self.client.get("/api/auth/me", headers={"Origin": FRONTEND}).status_code, 401)

    def test_preflight_and_write_origin_are_exact(self):
        good = self.client.options("/api/auth/login", headers={
            "Origin": FRONTEND, "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type"})
        self.assertEqual(good.status_code, 200)
        self.assertEqual(good.headers["access-control-allow-origin"], FRONTEND)
        bad = self.client.options("/api/auth/login", headers={
            "Origin": "https://attacker.example", "Access-Control-Request-Method": "POST"})
        self.assertNotEqual(bad.headers.get("access-control-allow-origin"), "https://attacker.example")
        payload = {"name": "Demo", "email": "demo@example.test", "password": "Safe-local-test-2026!"}
        self.assertEqual(self.client.post("/api/auth/register", json=payload).status_code, 403)
        self.assertEqual(self.client.post("/api/auth/register", json=payload,
                                          headers={"Origin": "https://attacker.example"}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
