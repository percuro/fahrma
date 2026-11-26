import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from app.web import create_application
from tests.support import ApiTestEnvironment


class WebTest(unittest.TestCase):
    def setUp(self):
        self.env = ApiTestEnvironment()
        self.env.create_user()
        self.dir = tempfile.TemporaryDirectory()
        dist = Path(self.dir.name)
        (dist / "assets").mkdir()
        (dist / "index.html").write_text("<!doctype html><title>app</title>")
        (dist / "assets" / "index-abc.js").write_text("console.log(1)")
        (dist / "sw.js").write_text("self.x=1")
        (dist / "manifest.webmanifest").write_text("{}")
        (dist / "icon.svg").write_text("<svg/>")
        self.client = TestClient(create_application(dist))

    def tearDown(self):
        self.env.close()
        self.dir.cleanup()

    def test_api_is_mounted_under_api(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(self.client.get("/api/v1/unknown").status_code, 404)

    def test_spa_fallback_and_cache_headers(self):
        for path in ("/", "/g/1/history", "/invite/abc"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertIn("<title>app</title>", response.text)
            self.assertEqual(response.headers["cache-control"], "no-cache")
        self.assertEqual(self.client.get("/sw.js").headers["cache-control"], "no-cache")
        asset = self.client.get("/assets/index-abc.js")
        self.assertIn("immutable", asset.headers["cache-control"])
        self.assertEqual(self.client.get("/assets/missing.js").status_code, 404)
        self.assertEqual(self.client.get("/missing.png").status_code, 404)
        manifest = self.client.get("/manifest.webmanifest")
        self.assertEqual(manifest.headers["content-type"], "application/manifest+json")

    def test_security_headers(self):
        for path in ("/", "/api/health"):
            headers = self.client.get(path).headers
            self.assertIn("frame-ancestors 'none'", headers["content-security-policy"])
            self.assertEqual(headers["x-content-type-options"], "nosniff")
            self.assertNotIn("strict-transport-security", headers)  # http PUBLIC_URL in tests

    def test_mounted_api_requires_csrf_header(self):
        bare = TestClient(self.client.app)
        response = bare.post("/api/v1/groups", json={"name": "x"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["code"], "csrf_rejected")

    def test_mounted_operator_api_needs_no_csrf_header(self):
        token = "o" * 40
        with mock.patch.dict("os.environ", {"OPERATOR_TOKEN": token}):
            bare = TestClient(self.client.app, headers={"Authorization": f"Bearer {token}"})
            # Reaches the operator API (no group 999) instead of being stopped by the CSRF check
            response = bare.put("/api/v1/operator/groups/999/plan", json={"plan": None})
            self.assertEqual(response.json()["detail"]["code"], "group_not_found")
            # Paths that merely contain the prefix are still checked
            response = bare.post("/api/v1/groups/v1/operator/x", json={})
            self.assertEqual(response.json()["detail"]["code"], "csrf_rejected")


if __name__ == "__main__":
    unittest.main()
