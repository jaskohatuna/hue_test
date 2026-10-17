"""The backend serves the built app without shadowing the API."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

import main
from test_api import running_api


def web_client(directory: Path) -> TestClient:
    app = FastAPI()

    @app.get("/api/ping")
    def ping():
        return {"ok": True}

    app.mount("/", main.AppFiles(directory=directory, html=True), name="app")
    return TestClient(app)


class WebAppTests(unittest.TestCase):
    def test_index_is_revalidated_and_hashed_assets_are_cached(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "assets").mkdir()
            (root / "index.html").write_text("<!doctype html><title>Moja svjetla</title>", encoding="utf-8")
            (root / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
            client = web_client(root)

            page = client.get("/")
            self.assertEqual(page.status_code, 200)
            self.assertIn("Moja svjetla", page.text)
            self.assertEqual(page.headers["cache-control"], "no-cache")

            asset = client.get("/assets/index-abc123.js")
            self.assertEqual(asset.status_code, 200)
            self.assertIn("immutable", asset.headers["cache-control"])

            self.assertEqual(client.get("/api/ping").json(), {"ok": True})
            self.assertEqual(client.get("/assets/missing.js").status_code, 404)

    def test_api_routes_take_precedence_over_the_app(self):
        if not main.WEB_DIR.is_dir():
            self.skipTest("app/dist is not built")
        with running_api() as (client, _, _):
            self.assertIn("text/html", client.get("/").headers["content-type"])
            self.assertEqual(client.get("/api/lights").status_code, 200)
            self.assertIn("configured", client.get("/api/setup").json())


if __name__ == "__main__":
    unittest.main()
