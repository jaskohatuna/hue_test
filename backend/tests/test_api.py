"""API checks against a simulated Hue transport, without a physical Bridge."""

import asyncio
from contextlib import contextmanager
from copy import deepcopy
import unittest
from unittest.mock import AsyncMock, call, patch

from aiohttp import ClientConnectionError, ClientResponseError
from aiohue import HueBridgeV2
from aiohue.errors import AiohueException, Unauthorized
from fastapi.testclient import TestClient

import main


LIGHT_ID = "7aa382e3-8431-4bf5-a863-ce5d5701731a"
SECOND_ID = "4061c22c-7c26-4629-8a92-79093feee33a"
APP_KEY = "secret-only-on-backend"


def resource(light_id=LIGHT_ID, name="Dnevna soba", on=False):
    return {
        "id": light_id,
        "type": "light",
        "metadata": {"name": name},
        "on": {"on": on},
        "owner": {"rid": "private-owner", "rtype": "device"},
    }


class HueTransport:
    """An in-memory Bridge HTTP boundary; aiohue itself still builds PUTs."""

    def __init__(self, resources):
        self.resources = {item["id"]: deepcopy(item) for item in resources}
        self.connectivity = []
        self.apply_commands = True

    async def request(self, method, path, **kwargs):
        prefix = "clip/v2/resource/light"
        if method == "get" and path == "clip/v2/resource/zigbee_connectivity":
            return deepcopy(self.connectivity)
        if method == "get" and path == prefix:
            return deepcopy(list(self.resources.values()))
        if path.startswith(prefix + "/"):
            light_id = path.rsplit("/", 1)[1]
            item = self.resources.get(light_id)
            if method == "get":
                return [deepcopy(item)] if item else []
            if method == "put":
                if item and self.apply_commands:
                    body = kwargs["json"]
                    if "on" in body:
                        item["on"] = deepcopy(body["on"])
                    if "dimming" in body:
                        item.setdefault("dimming", {}).update(body["dimming"])
                return [{"rid": light_id, "rtype": "light"}]
        raise AssertionError(f"Unexpected Hue request: {method} {path}")


@contextmanager
def running_api(resources=None):
    transport = HueTransport(resources if resources is not None else [resource()])
    # The real controller verifies our use of the installed aiohue API and its
    # on/off serialization. Only the network boundary and shutdown are mocked.
    bridge = HueBridgeV2("192.0.2.10", APP_KEY)
    bridge.request = AsyncMock(side_effect=transport.request)
    bridge.close = AsyncMock()
    with (
        patch.object(main, "read_config", return_value=("192.0.2.10", APP_KEY)),
        patch.object(main, "HueBridgeV2", return_value=bridge),
    ):
        try:
            with TestClient(main.app) as client:
                yield client, bridge, transport
        finally:
            bridge.close.assert_awaited_once_with()


class LightsApiTests(unittest.TestCase):
    def test_get_fetches_fresh_state_and_exposes_only_public_fields(self):
        fixtures = [resource(name="Spavaca soba"), resource(SECOND_ID, "Dnevna soba", True)]
        with running_api(fixtures) as (client, bridge, transport):
            first = client.get("/api/lights")
            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.headers["cache-control"], "no-store")
            self.assertEqual(first.json(), [
                {"id": SECOND_ID, "name": "Dnevna soba", "on": True},
                {"id": LIGHT_ID, "name": "Spavaca soba", "on": False},
            ])
            transport.resources[LIGHT_ID]["on"]["on"] = True
            second = client.get("/api/lights")
            self.assertTrue(second.json()[1]["on"])
            self.assertNotIn(APP_KEY, second.text)
            self.assertNotIn("private-owner", second.text)
            self.assertEqual(bridge.request.await_args_list, [
                call("get", "clip/v2/resource/light"),
                call("get", "clip/v2/resource/zigbee_connectivity"),
                call("get", "clip/v2/resource/light"),
                call("get", "clip/v2/resource/zigbee_connectivity"),
            ])

    def test_put_serializes_with_aiohue_and_reads_state_after_each_command(self):
        path = f"clip/v2/resource/light/{LIGHT_ID}"
        with running_api() as (client, bridge, _):
            for on in (True, False):
                with self.subTest(on=on):
                    response = client.put(f"/api/lights/{LIGHT_ID}", json={"on": on})
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.headers["cache-control"], "no-store")
                    self.assertEqual(response.json(), {
                        "id": LIGHT_ID, "name": "Dnevna soba", "on": on,
                    })
            self.assertEqual(bridge.request.await_args_list, [
                call("put", path, json={"on": {"on": True}}),
                call("get", path),
                call("get", "clip/v2/resource/zigbee_connectivity"),
                call("put", path, json={"on": {"on": False}}),
                call("get", path),
                call("get", "clip/v2/resource/zigbee_connectivity"),
            ])

    def test_put_returns_bridge_snapshot_instead_of_echoing_requested_state(self):
        with running_api() as (client, _, transport):
            transport.apply_commands = False
            response = client.put(f"/api/lights/{LIGHT_ID}", json={"on": True})
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json()["on"])

    def test_invalid_commands_and_ids_never_reach_bridge(self):
        invalid_bodies = [
            {}, {"on": "true"}, {"on": 1}, {"on": None},
            {"on": True, "color": "red"},
        ]
        with running_api() as (client, bridge, _):
            for body in invalid_bodies:
                with self.subTest(body=body):
                    response = client.put(f"/api/lights/{LIGHT_ID}", json=body)
                    self.assertEqual(response.status_code, 422)
            response = client.put("/api/lights/not-a-uuid", json={"on": True})
            self.assertEqual(response.status_code, 422)
            bridge.request.assert_not_awaited()

    def test_missing_light_is_404(self):
        with running_api([]) as (client, _, _):
            response = client.put(f"/api/lights/{LIGHT_ID}", json={"on": True})
            self.assertEqual(response.status_code, 404)
            self.assertIn("Svjetlo", response.json()["detail"])

    def test_hue_http_404_is_404(self):
        with running_api() as (client, bridge, _):
            bridge.request.side_effect = ClientResponseError(None, (), status=404)
            response = client.put(f"/api/lights/{LIGHT_ID}", json={"on": False})
            self.assertEqual(response.status_code, 404)

    def test_errors_are_friendly_hide_secrets_and_allow_next_request(self):
        failures = [
            (ClientConnectionError(APP_KEY), 503, "Bridge nije dostupan"),
            (TimeoutError(APP_KEY), 503, "Bridge nije dostupan"),
            (Unauthorized(APP_KEY), 503, "API"),
            (AiohueException(APP_KEY), 502, "Bridge nije mogao"),
        ]
        for failure, status, message in failures:
            with self.subTest(failure=type(failure).__name__):
                with running_api() as (client, bridge, _):
                    bridge.request.side_effect = [failure, [resource(on=True)], []]
                    failed = client.get("/api/lights")
                    self.assertEqual(failed.status_code, status)
                    self.assertIn(message, failed.json()["detail"])
                    self.assertNotIn(APP_KEY, failed.text)
                    recovered = client.get("/api/lights")
                    self.assertEqual(recovered.status_code, 200)
                    self.assertTrue(recovered.json()[0]["on"])

    def test_timeout_actually_bounds_slow_bridge_and_connection_is_reusable(self):
        async def slow_request(*args, **kwargs):
            await asyncio.sleep(1)
            return []

        with running_api() as (client, bridge, transport):
            bridge.request.side_effect = slow_request
            with patch.object(main, "BRIDGE_TIMEOUT", 0.01):
                response = client.get("/api/lights")
            self.assertEqual(response.status_code, 503)
            self.assertIn("Bridge nije dostupan", response.json()["detail"])
            bridge.request.side_effect = transport.request
            self.assertEqual(client.get("/api/lights").status_code, 200)

    def test_shutdown_closes_bridge_after_failed_request(self):
        with running_api() as (client, bridge, _):
            bridge.request.side_effect = ClientConnectionError("offline")
            self.assertEqual(client.get("/api/lights").status_code, 503)
            bridge.close.assert_not_awaited()
        bridge.close.assert_awaited_once_with()

    def test_missing_or_invalid_configuration_keeps_api_available(self):
        for configuration in [("", ""), ("192.0.2.10", ""), ("https://invalid", APP_KEY)]:
            with self.subTest(configuration=configuration):
                with (
                    patch.object(main, "read_config", return_value=configuration),
                    patch.object(main, "HueBridgeV2") as constructor,
                    TestClient(main.app) as client,
                ):
                    response = client.get("/api/lights")
                    self.assertEqual(response.status_code, 503)
                    self.assertTrue(
                        any(word in response.json()["detail"].casefold() for word in ("pove", "postav")),
                    )
                    self.assertNotIn(APP_KEY, response.text)
                    constructor.assert_not_called()

    def test_power_cut_is_unavailable_without_inventing_an_off_state(self):
        with running_api([resource(on=True)]) as (client, _, transport):
            transport.connectivity = [{
                "id": "connectivity-service-id",
                "type": "zigbee_connectivity",
                "owner": {"rid": "private-owner", "rtype": "device"},
                "status": "connectivity_issue",
            }]
            response = client.get("/api/lights")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()[0], {
                "id": LIGHT_ID, "name": "Dnevna soba", "on": True, "available": False,
            })
            # A recovered device is reflected by the next fresh GET, without
            # changing the Bridge's remembered on/off state.
            transport.connectivity[0]["status"] = "connected"
            recovered = client.get("/api/lights").json()[0]
            self.assertTrue(recovered["available"])
            self.assertTrue(recovered["on"])
            changed = client.put(f"/api/lights/{LIGHT_ID}", json={"on": False}).json()
            self.assertTrue(changed["available"])
            self.assertFalse(changed["on"])

    def test_only_known_connectivity_states_determine_availability(self):
        statuses = [
            ("connected", True), ("disconnected", False), ("connectivity_issue", False),
            ("unidirectional_incoming", None), ("pending_discovery", None), ("future-status", None),
        ]
        with running_api([resource(on=True)]) as (client, _, transport):
            for status, available in statuses:
                with self.subTest(status=status):
                    transport.connectivity = [{
                        "id": "different-from-light-id", "type": "zigbee_connectivity",
                        "owner": {"rid": "private-owner", "rtype": "device"}, "status": status,
                    }]
                    snapshot = client.get("/api/lights").json()[0]
                    self.assertTrue(snapshot["on"])
                    if available is None:
                        self.assertNotIn("available", snapshot)
                    else:
                        self.assertIs(snapshot["available"], available)


if __name__ == "__main__":
    unittest.main()
