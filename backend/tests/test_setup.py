"""Bridge setup is transactional: validate, save, then replace the active client."""

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, call, patch

from aiohttp import ClientConnectionError
from aiohue import HueBridgeV2
from aiohue.errors import LinkButtonNotPressed, Unauthorized
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

import main
from test_api import APP_KEY, LIGHT_ID, resource


NEW_IP = "192.0.2.20"
NEW_KEY = "new-private-application-key"


def simulated_bridge(ip, key, name):
    bridge = HueBridgeV2(ip, key)
    bridge.request = AsyncMock(return_value=[resource(name=name)])
    bridge.close = AsyncMock()
    return bridge


@contextmanager
def setup_api(initial=("192.0.2.10", APP_KEY)):
    old = simulated_bridge("192.0.2.10", APP_KEY, "Staro svjetlo")
    candidate = simulated_bridge(NEW_IP, NEW_KEY, "Novo svjetlo")
    bridges = [old, candidate] if all(initial) else [candidate]
    with (
        patch.object(main, "read_config", return_value=initial),
        patch.object(main, "HueBridgeV2", side_effect=bridges) as constructor,
        patch.object(main, "create_app_key", new_callable=AsyncMock) as register,
        patch.object(main, "write_config") as save,
    ):
        register.return_value = NEW_KEY
        with TestClient(main.app) as client:
            yield SimpleNamespace(
                client=client, old=old, candidate=candidate,
                constructor=constructor, register=register, save=save,
            )


class SetupApiTests(unittest.TestCase):
    def assert_old_connection_preserved(self, state):
        self.assertIs(main.app.state.bridge, state.old)
        self.assertEqual(main.app.state.bridge_ip, "192.0.2.10")
        state.old.close.assert_not_awaited()
        self.assertEqual(state.client.get("/api/lights").json()[0]["name"], "Staro svjetlo")

    def test_status_reports_public_configuration_without_contacting_bridge(self):
        for initial in [("", ""), ("192.0.2.10", ""), ("192.0.2.10", APP_KEY)]:
            with self.subTest(initial=initial):
                with setup_api(initial) as state:
                    response = state.client.get("/api/setup")
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json(), {
                        "bridge_ip": initial[0], "configured": bool(all(initial)),
                    })
                    self.assertNotIn(APP_KEY, response.text)
                    state.old.request.assert_not_awaited()
                    state.candidate.request.assert_not_awaited()
                    state.register.assert_not_awaited()

    def test_manual_key_is_validated_saved_and_used_immediately(self):
        with setup_api() as state:
            response = state.client.post("/api/setup", json={
                "bridge_ip": NEW_IP, "app_key": NEW_KEY,
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"bridge_ip": NEW_IP, "configured": True})
            self.assertNotIn(NEW_KEY, response.text)
            self.assertNotIn(APP_KEY, response.text)
            state.register.assert_not_awaited()
            state.constructor.assert_has_calls([
                call("192.0.2.10", APP_KEY), call(NEW_IP, NEW_KEY),
            ])
            state.candidate.request.assert_awaited_once_with("get", "clip/v2/resource/light")
            state.save.assert_called_once_with(NEW_IP, NEW_KEY)
            state.old.close.assert_awaited_once_with()
            state.candidate.close.assert_not_awaited()
            self.assertEqual(state.client.get("/api/lights").json()[0]["name"], "Novo svjetlo")
            self.assertEqual(state.client.get("/api/setup").json(), response.json())
        state.candidate.close.assert_awaited_once_with()
        state.old.close.assert_awaited_once_with()

    def test_missing_null_or_blank_key_registers_after_bridge_button(self):
        for supplied_key in ("omitted", None, "", "   "):
            with self.subTest(supplied_key=supplied_key):
                with setup_api(initial=("", "")) as state:
                    body = {"bridge_ip": NEW_IP}
                    if supplied_key != "omitted":
                        body["app_key"] = supplied_key
                    response = state.client.post("/api/setup", json=body)
                    self.assertEqual(response.status_code, 200)
                    state.register.assert_awaited_once_with(NEW_IP, "local-hue#mobile")
                    state.constructor.assert_called_once_with(NEW_IP, NEW_KEY)
                    state.candidate.request.assert_awaited_once_with("get", "clip/v2/resource/light")
                    state.save.assert_called_once_with(NEW_IP, NEW_KEY)
                    self.assertNotIn(NEW_KEY, response.text)
                state.candidate.close.assert_awaited_once_with()

    def test_registration_failure_preserves_existing_connection_and_config(self):
        failures = [
            (LinkButtonNotPressed(NEW_KEY), 400),
            (ClientConnectionError(NEW_KEY), 503),
            (TimeoutError(NEW_KEY), 503),
        ]
        for failure, status in failures:
            with self.subTest(failure=type(failure).__name__):
                with setup_api() as state:
                    state.register.side_effect = failure
                    response = state.client.post("/api/setup", json={"bridge_ip": NEW_IP})
                    self.assertEqual(response.status_code, status)
                    self.assertIsInstance(response.json()["detail"], str)
                    self.assertNotIn(NEW_KEY, response.text)
                    state.save.assert_not_called()
                    state.constructor.assert_called_once_with("192.0.2.10", APP_KEY)
                    self.assert_old_connection_preserved(state)

    def test_candidate_validation_failure_closes_candidate_and_preserves_previous_setup(self):
        failures = [Unauthorized(NEW_KEY), ClientConnectionError(NEW_KEY), TimeoutError(NEW_KEY)]
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                with setup_api() as state:
                    state.candidate.request.side_effect = failure
                    response = state.client.post("/api/setup", json={
                        "bridge_ip": NEW_IP, "app_key": NEW_KEY,
                    })
                    self.assertEqual(response.status_code, 503)
                    self.assertNotIn(NEW_KEY, response.text)
                    state.save.assert_not_called()
                    state.candidate.close.assert_awaited_once_with()
                    self.assert_old_connection_preserved(state)
                state.candidate.close.assert_awaited_once_with()

    def test_file_write_failure_closes_candidate_and_keeps_old_connection(self):
        with setup_api() as state:
            state.save.side_effect = PermissionError(NEW_KEY)
            response = state.client.post("/api/setup", json={
                "bridge_ip": NEW_IP, "app_key": NEW_KEY,
            })
            self.assertEqual(response.status_code, 500)
            self.assertIsInstance(response.json()["detail"], str)
            self.assertNotIn(NEW_KEY, response.text)
            state.candidate.close.assert_awaited_once_with()
            self.assert_old_connection_preserved(state)

    def test_validation_errors_never_echo_submitted_keys(self):
        invalid_bodies = [
            {"bridge_ip": "https://192.0.2.20", "app_key": NEW_KEY},
            {"bridge_ip": "", "app_key": NEW_KEY},
            {"app_key": NEW_KEY},
            {"bridge_ip": NEW_IP, "app_key": NEW_KEY, "unexpected": NEW_KEY},
            {"bridge_ip": NEW_IP, "app_key": {"secret": NEW_KEY}},
        ]
        with setup_api() as state:
            for body in invalid_bodies:
                with self.subTest(body=body):
                    response = state.client.post("/api/setup", json=body)
                    self.assertEqual(response.status_code, 422)
                    self.assertIsInstance(response.json()["detail"], str)
                    self.assertNotIn(NEW_KEY, response.text)
            response = state.client.put(f"/api/lights/{LIGHT_ID}", json={
                "on": True, "accidental_key": NEW_KEY,
            })
            self.assertEqual(response.status_code, 422)
            self.assertNotIn(NEW_KEY, response.text)
            state.save.assert_not_called()
            state.register.assert_not_awaited()
            state.candidate.request.assert_not_awaited()

    def test_replacement_and_old_connection_close_happen_under_lock(self):
        with setup_api() as state:
            def save_under_lock(*args):
                self.assertTrue(main.app.state.bridge_lock.locked())

            async def close_under_lock():
                self.assertTrue(main.app.state.bridge_lock.locked())

            state.save.side_effect = save_under_lock
            state.old.close.side_effect = close_under_lock
            response = state.client.post("/api/setup", json={
                "bridge_ip": NEW_IP, "app_key": NEW_KEY,
            })
            self.assertEqual(response.status_code, 200)
            self.assertIs(main.app.state.bridge, state.candidate)

    def test_waiting_light_requests_use_replacement_after_acquiring_lock(self):
        for method in ("get", "put"):
            with self.subTest(method=method):
                with setup_api() as state:
                    async def scenario():
                        transport = ASGITransport(app=main.app)
                        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                            async with main.app.state.bridge_lock:
                                operation = (
                                    client.get("/api/lights") if method == "get" else
                                    client.put(f"/api/lights/{LIGHT_ID}", json={"on": True})
                                )
                                pending = asyncio.create_task(operation)
                                # Let the route run until it waits for the shared lock.
                                await asyncio.sleep(0)
                                state.old.request.assert_not_awaited()
                                main.app.state.bridge = state.candidate
                                main.app.state.bridge_ip = NEW_IP
                            response = await asyncio.wait_for(pending, timeout=2)
                            self.assertEqual(response.status_code, 200)
                            reported = response.json()[0] if method == "get" else response.json()
                            self.assertEqual(reported["name"], "Novo svjetlo")
                            state.old.request.assert_not_awaited()
                            await state.old.close()

                    state.client.portal.call(scenario)
                state.candidate.close.assert_awaited_once_with()


if __name__ == "__main__":
    unittest.main()
