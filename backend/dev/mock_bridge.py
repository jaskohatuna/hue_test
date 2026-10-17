"""Simulated Hue Bridge (API V2) for testing the app without real lights.

Start from the backend folder:
    .\\.venv\\Scripts\\python.exe dev\\mock_bridge.py

Then connect the app to Bridge IP 127.0.0.1 with the "button" mode; the
simulated link button is always pressed. Changes made directly on the mock
(e.g. with curl) are sent to the backend through the event stream, just like
changes from a wall switch or the Hue app.
"""

import argparse
import asyncio
import datetime
import json
import ssl
import sys
import tempfile
import uuid
from itertools import count
from pathlib import Path

from aiohttp import web
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

# Name, on, connectivity, brightness (None = cannot be dimmed, e.g. a smart plug).
LIGHTS = [
    ("Dnevna soba", True, "connected", 80.0),
    ("Kuhinja", False, "connected", 100.0),
    ("Spavaća soba", True, "connected", 24.8),
    ("Hodnik", True, "connectivity_issue", 60.0),
    ("Lampa za čitanje", False, "connected", 45.0),
    ("Utičnica", False, "connected", None),
]


class MockBridge:
    def __init__(self, app_key: str | None):
        self.app_keys = {app_key} if app_key else set()
        self.lights = {}
        self.connectivity = []
        self.listeners: set[asyncio.Queue] = set()
        self.event_ids = count(1)
        for name, on, status, brightness in LIGHTS:
            light_id, device_id = str(uuid.uuid4()), str(uuid.uuid4())
            owner = {"rid": device_id, "rtype": "device"}
            self.lights[light_id] = {
                "id": light_id, "type": "light", "owner": owner,
                "metadata": {"name": name}, "on": {"on": on},
            }
            if brightness is not None:
                self.lights[light_id]["dimming"] = {"brightness": brightness, "min_dim_level": 0.2}
            self.connectivity.append({
                "id": str(uuid.uuid4()), "type": "zigbee_connectivity",
                "owner": owner, "status": status,
            })

    def authorized(self, request: web.Request) -> bool:
        return request.headers.get("hue-application-key") in self.app_keys

    @staticmethod
    def data(items, status=200):
        return web.json_response({"errors": [], "data": items}, status=status)

    @staticmethod
    def error(status, description):
        return web.json_response({"errors": [{"description": description}], "data": []}, status=status)

    async def pair(self, request: web.Request):
        body = await request.json()
        if not isinstance(body, dict) or not body.get("devicetype"):
            return web.json_response([{"error": {"type": 7, "description": "invalid value"}}])
        key = uuid.uuid4().hex
        self.app_keys.add(key)
        print(f"Novo uparivanje: {body['devicetype']}")
        return web.json_response([{"success": {"username": key}}])

    async def resource(self, request: web.Request):
        if not self.authorized(request):
            return self.error(403, "unauthorized user")
        kind = request.match_info["kind"]
        if kind == "zigbee_connectivity":
            return self.data(self.connectivity)
        if kind == "light":
            return self.data(list(self.lights.values()))
        return self.error(404, "resource not found")

    async def light(self, request: web.Request):
        if not self.authorized(request):
            return self.error(403, "unauthorized user")
        light = self.lights.get(request.match_info["light_id"])
        if light is None:
            return self.error(404, "resource not found")
        if request.method == "GET":
            return self.data([light])
        body = await request.json()
        if not isinstance(body, dict):
            return self.error(400, "invalid body")
        change = {}
        if "on" in body:
            if not isinstance(body["on"], dict) or not isinstance(body["on"].get("on"), bool):
                return self.error(400, "invalid body")
            change["on"] = {"on": body["on"]["on"]}
        if "dimming" in body:
            brightness = body["dimming"].get("brightness") if isinstance(body["dimming"], dict) else None
            if "dimming" not in light:
                return self.error(400, "device (light) has no dimming feature")
            if not isinstance(brightness, (int, float)) or not 0 <= brightness <= 100:
                return self.error(400, "invalid body")
            # Like a real Bridge: 0 means the lowest level, not off.
            change["dimming"] = {"brightness": max(float(brightness), light["dimming"]["min_dim_level"])}
        if not change:
            return self.error(400, "invalid body")
        self.update_light(light, change)
        return self.data([{"rid": light["id"], "rtype": "light"}])

    def update_light(self, light: dict, change: dict) -> None:
        for key, value in change.items():
            light[key].update(value)
        state = "uključeno" if light["on"]["on"] else "isključeno"
        if "dimming" in light:
            state += f", {light['dimming']['brightness']:.0f} %"
        print(f"{light['metadata']['name']}: {state}")
        event = [{
            "creationtime": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "id": str(uuid.uuid4()),
            "type": "update",
            "data": [{"id": light["id"], "owner": light["owner"], "type": "light", **change}],
        }]
        for queue in self.listeners:
            queue.put_nowait(event)

    async def eventstream(self, request: web.Request):
        if not self.authorized(request):
            return self.error(403, "unauthorized user")
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        queue = asyncio.Queue()
        self.listeners.add(queue)
        try:
            await response.write(b": hi\n\n")
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                except TimeoutError:
                    await response.write(b": keep-alive\n\n")
                    continue
                payload = f"id: {next(self.event_ids)}:0\ndata: {json.dumps(event)}\n\n"
                await response.write(payload.encode())
        finally:
            self.listeners.discard(queue)
        return response

    def routes(self) -> web.Application:
        app = web.Application()
        app.router.add_post("/api", self.pair)
        app.router.add_get("/clip/v2/resource/light/{light_id}", self.light)
        app.router.add_put("/clip/v2/resource/light/{light_id}", self.light)
        app.router.add_get("/clip/v2/resource/{kind}", self.resource)
        app.router.add_get("/eventstream/clip/v2", self.eventstream)
        return app


def self_signed_context() -> ssl.SSLContext:
    """Like a real Bridge, the mock uses a certificate that clients do not verify."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "mock-hue-bridge")])
    now = datetime.datetime.now(datetime.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    with tempfile.TemporaryDirectory() as folder:
        cert_path, key_path = Path(folder, "cert.pem"), Path(folder, "key.pem")
        cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(cert_path, key_path)
    return context


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1", help="IP adresa simuliranog Bridgea")
    parser.add_argument("--port", type=int, default=443, help="aiohue uvijek koristi HTTPS port 443")
    parser.add_argument("--app-key", help="dodatni API ključ koji Bridge prihvata")
    args = parser.parse_args()
    # Light names contain č/ć; redirected Windows output would otherwise use cp1252.
    sys.stdout.reconfigure(encoding="utf-8")

    bridge = MockBridge(args.app_key)
    print(f"Simulirani Hue Bridge: https://{args.host}:{args.port}")
    for light in bridge.lights.values():
        print(f"  {light['id']}  {light['metadata']['name']}")
    web.run_app(
        bridge.routes(), host=args.host, port=args.port,
        ssl_context=self_signed_context(), print=None,
    )


if __name__ == "__main__":
    main()
