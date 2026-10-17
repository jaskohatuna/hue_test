"""CORS checks: only the mobile app and the dev server may call the API from a browser."""

import unittest

from test_api import LIGHT_ID, running_api


class CorsTests(unittest.TestCase):
    def test_app_origins_may_read_and_send_commands(self):
        with running_api() as (client, _, _):
            for origin in ("capacitor://localhost", "http://localhost", "http://localhost:5173"):
                with self.subTest(origin=origin):
                    preflight = client.options(f"/api/lights/{LIGHT_ID}", headers={
                        "Origin": origin,
                        "Access-Control-Request-Method": "PUT",
                        "Access-Control-Request-Headers": "content-type",
                    })
                    self.assertEqual(preflight.status_code, 200)
                    self.assertEqual(preflight.headers["access-control-allow-origin"], origin)
                    self.assertIn("PUT", preflight.headers["access-control-allow-methods"])

                    response = client.get("/api/lights", headers={"Origin": origin})
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.headers["access-control-allow-origin"], origin)

    def test_error_responses_keep_cors_headers(self):
        with running_api() as (client, _, _):
            response = client.put(
                "/api/lights/not-a-uuid", json={"on": True}, headers={"Origin": "http://localhost"}
            )
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost")

    def test_other_websites_are_not_allowed(self):
        with running_api() as (client, _, _):
            preflight = client.options(f"/api/lights/{LIGHT_ID}", headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "PUT",
            })
            self.assertEqual(preflight.status_code, 400)
            self.assertNotIn("access-control-allow-origin", preflight.headers)
            response = client.get("/api/lights", headers={"Origin": "https://example.com"})
            self.assertNotIn("access-control-allow-origin", response.headers)


if __name__ == "__main__":
    unittest.main()
