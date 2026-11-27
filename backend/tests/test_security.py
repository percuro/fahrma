import os
import unittest

from fastapi import HTTPException, Request
from fastapi.responses import Response

from app.middleware.csrf import enforce_csrf
from app.services.login_rate_limiter import LoginRateLimiter


class LoginRateLimiterTest(unittest.TestCase):
    def test_blocks_account_after_five_failures(self):
        limiter = LoginRateLimiter("test")
        for _ in range(5):
            limiter.check("alex", "192.0.2.1")
            limiter.record_failure("alex", "192.0.2.1")

        with self.assertRaises(HTTPException) as context:
            limiter.check("alex", "192.0.2.1")
        self.assertEqual(context.exception.status_code, 429)
        self.assertEqual(context.exception.detail["code"], "too_many_attempts")

        limiter.record_success("alex")
        limiter.check("alex", "192.0.2.1")

    def test_reports_the_block_once(self):
        limiter = LoginRateLimiter("test", account_limit=3)
        reported = [limiter.record_failure("alex", "192.0.2.1") for _ in range(5)]
        self.assertEqual(reported, [False, False, True, False, False])

    def test_blocks_ip_after_twenty_failures(self):
        limiter = LoginRateLimiter("test")
        for i in range(20):
            limiter.record_failure(f"user{i}", "192.0.2.9")
        with self.assertRaises(HTTPException):
            limiter.check("neu", "192.0.2.9")


class CsrfMiddlewareTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.previous = {k: os.environ.get(k) for k in ("CSRF_PROTECTION", "CORS_ORIGINS", "PUBLIC_URL")}
        os.environ["CSRF_PROTECTION"] = "true"
        os.environ["PUBLIC_URL"] = "https://cars.example.org"
        os.environ["CORS_ORIGINS"] = ""

    async def asyncTearDown(self):
        for key, value in self.previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    async def _call(self, method: str, headers: dict[str, str]) -> int:
        request = Request(
            {
                "type": "http",
                "method": method,
                "path": "/v1/groups/1/trips/1",
                "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            }
        )

        async def call_next(_request):
            return Response(status_code=200)

        return (await enforce_csrf(request, call_next)).status_code

    async def test_get_is_allowed_without_header(self):
        self.assertEqual(await self._call("GET", {}), 200)

    async def test_put_requires_header_and_trusted_origin(self):
        self.assertEqual(await self._call("PUT", {}), 403)
        self.assertEqual(await self._call("PUT", {"X-Carshare-CSRF": "1"}), 403)
        self.assertEqual(await self._call("PUT", {"X-Carshare-CSRF": "1", "Origin": "https://evil.example"}), 403)
        self.assertEqual(await self._call("PUT", {"X-Carshare-CSRF": "1", "Origin": "https://cars.example.org"}), 200)
        self.assertEqual(
            await self._call("PUT", {"X-Carshare-CSRF": "1", "Referer": "https://cars.example.org/history"}),
            200,
        )


if __name__ == "__main__":
    unittest.main()


class BodyLimitTest(unittest.TestCase):
    def setUp(self):
        from tests.support import ApiTestEnvironment

        self.env = ApiTestEnvironment()
        self.env.create_user("alex")
        self.client = self.env.client("alex")

    def tearDown(self):
        self.env.close()

    def test_large_json_is_refused_before_it_is_read(self):
        body = b'{"display_name": "' + b"x" * (1024 * 1024) + b'"}'
        response = self.client.patch("/v1/auth/me", content=body, headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["detail"]["code"], "request_too_large")
        self.assertEqual(response.json()["detail"]["params"], {"max_kb": 1024})

    def test_body_without_length_is_refused(self):
        def chunks():
            yield b'{"display_name": "Alex"}'

        response = self.client.patch("/v1/auth/me", content=chunks(), headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 411)
        self.assertEqual(response.json()["detail"]["code"], "length_required")

    def test_uploads_keep_their_own_limit(self):
        """A group export may be larger than 1 MB; the import checks it while reading."""
        body = b"[" + b" " * (2 * 1024 * 1024) + b"]"
        json_type = {"Content-Type": "application/json"}
        response = self.client.post("/v1/groups/import/check", content=body, headers=json_type)
        self.assertNotIn(response.status_code, (411, 413), response.text)

    def test_small_requests_pass(self):
        response = self.client.patch("/v1/auth/me", json={"display_name": "Alex"})
        self.assertEqual(response.status_code, 200, response.text)
