"""Simulated Hue event streams; these checks never contact a real Bridge."""

import asyncio
from contextlib import asynccontextmanager
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from aiohttp import ClientResponseError
from aiohue import HueBridgeV2
from fastapi.testclient import TestClient

import main
from realtime import HueEventStream
from test_api import APP_KEY, HueTransport, resource


EOF = object()


class SimulatedSSE:
    def __init__(self, status=200):
        self.status = status
        self.headers = {"Content-Type": "text/event-stream"}
        self.content = self
        self.lines = asyncio.Queue()
        self.closed = asyncio.Event()

    def raise_for_status(self):
        if self.status >= 400:
            raise ClientResponseError(None, (), status=self.status, message=APP_KEY)

    def __aiter__(self):
        return self

    async def __anext__(self):
        line = await self.lines.get()
        if line is EOF:
            raise StopAsyncIteration
        return line

    def event(self, item, event_type="update", event_id=None):
        if event_id:
            self.lines.put_nowait(f"id: {event_id}\n".encode())
        data = json.dumps([{"type": event_type, "data": [item]}])
        self.lines.put_nowait(f"data: {data}\n".encode())
        self.lines.put_nowait(b"\n")


class SimulatedBridge:
    def __init__(self, *connections):
        self.connections = list(connections)
        self.opened = asyncio.Queue()
        self.calls = []

    @asynccontextmanager
    async def create_request(self, method, path, **kwargs):
        connection = self.connections.pop(0)
        self.calls.append((method, path, dict(kwargs["headers"])))
        self.opened.put_nowait(connection)
        try:
            yield connection
        finally:
            connection.closed.set()


async def matching_message(queue, *, connected, timeout=3):
    async def receive():
        while True:
            message = await queue.get()
            if message["connected"] is connected:
                return message

    return await asyncio.wait_for(receive(), timeout)


class EventStreamTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.connection = SimulatedSSE()
        self.bridge = SimulatedBridge(self.connection)
        self.state = SimpleNamespace(bridge=self.bridge, bridge_ip="192.0.2.10")
        self.stream = HueEventStream(self.state)

    async def asyncTearDown(self):
        await self.stream.close()

    async def subscribe_connected(self):
        queue = await self.stream.subscribe()
        await matching_message(queue, connected=True)
        return queue

    async def test_no_subscribers_means_no_connection_and_two_tabs_share_one_reader(self):
        await asyncio.sleep(0)
        self.assertEqual(self.bridge.calls, [])
        first = await self.subscribe_connected()
        second = await self.subscribe_connected()
        self.assertEqual(len(self.bridge.calls), 1)
        task = self.stream.task
        self.connection.event({"id": "light-id", "type": "light", "on": {"on": True}})
        for queue in (first, second):
            update = await matching_message(queue, connected=True)
            self.assertEqual(set(update), {"type", "connected", "configured", "bridge_ip", "detail"})
            self.assertEqual(update["type"], "bridge_update")
            self.assertNotIn(APP_KEY, json.dumps(update))
        await self.stream.unsubscribe(first)
        self.assertIs(self.stream.task, task)
        self.assertFalse(self.connection.closed.is_set())
        await self.stream.unsubscribe(second)
        self.assertTrue(self.connection.closed.is_set())
        self.assertTrue(task.done())
        self.assertIsNone(self.stream.task)

    async def test_parser_survives_malformed_input_and_invalidates_for_relevant_resources(self):
        queue = await self.subscribe_connected()
        for line in (b": keepalive\n", b"\xff\n", b"data: broken-json\n", b"\n"):
            self.connection.lines.put_nowait(line)
        # A valid multiline SSE event must still arrive after the bad event.
        for line in (
            b"data: [\n", b'data: {"type":"update","data":[{"type":"light"}]}]\n', b"\n",
        ):
            self.connection.lines.put_nowait(line)
        self.assertTrue((await matching_message(queue, connected=True))["configured"])
        for item, event_type in [
            ({"type": "zigbee_connectivity", "status": "disconnected"}, "update"),
            ({"type": "device", "id": "device-id"}, "add"),
            ({"rtype": "light", "rid": "deleted-id"}, "delete"),
        ]:
            self.connection.event(item, event_type)
            await matching_message(queue, connected=True)
        self.connection.event({"type": "temperature", "temperature": 22})
        await asyncio.sleep(0.01)
        self.assertTrue(queue.empty())
        self.assertFalse(self.stream.task.done())

    async def test_reconnect_resumes_last_id_and_notifies_browser_to_refresh(self):
        second = SimulatedSSE()
        self.bridge.connections.append(second)
        queue = await self.subscribe_connected()
        self.connection.event({"type": "light"}, event_id="last-event-42")
        await matching_message(queue, connected=True)
        self.connection.lines.put_nowait(EOF)
        disconnected = await matching_message(queue, connected=False)
        self.assertIsInstance(disconnected["detail"], str)
        reconnected = await matching_message(queue, connected=True)
        self.assertTrue(reconnected["configured"])
        self.assertEqual(len(self.bridge.calls), 2)
        headers = {key.lower(): value for key, value in self.bridge.calls[1][2].items()}
        self.assertEqual(headers["last-event-id"], "last-event-42")
        self.assertEqual(headers["accept"], "text/event-stream")
        self.assertTrue(self.connection.closed.is_set())

    async def test_auth_failure_is_sanitized_and_shutdown_cancels_retry(self):
        self.connection.status = 403
        queue = await self.stream.subscribe()
        # subscribe() first queues a neutral status; wait for the auth failure.
        async def failure_message():
            while True:
                message = await queue.get()
                if message["detail"]:
                    return message

        message = await asyncio.wait_for(failure_message(), timeout=2)
        self.assertFalse(message["connected"])
        self.assertIn("API", message["detail"])
        self.assertNotIn(APP_KEY, json.dumps(message))
        task = self.stream.task
        await self.stream.close()
        self.assertTrue(task.done())
        self.assertIsNone(self.stream.task)
        self.assertTrue(self.connection.closed.is_set())

    async def test_restart_stops_old_reader_before_switching_bridge(self):
        queue = await self.subscribe_connected()
        old_task = self.stream.task
        second = SimulatedSSE()
        replacement = SimulatedBridge(second)
        self.state.bridge = replacement
        self.state.bridge_ip = "192.0.2.20"
        await self.stream.restart()
        self.assertTrue(old_task.done())
        self.assertTrue(self.connection.closed.is_set())
        update = await matching_message(queue, connected=True)
        self.assertEqual(update["bridge_ip"], "192.0.2.20")
        self.assertEqual(len(self.bridge.calls), 1)
        self.assertEqual(len(replacement.calls), 1)
        new_task = self.stream.task
        await self.stream.close()
        self.assertTrue(new_task.done())
        self.assertTrue(second.closed.is_set())

    async def test_last_disconnect_racing_new_subscriber_leaves_one_reader(self):
        previous = await self.subscribe_connected()
        old_task = self.stream.task
        self.bridge.connections.append(SimulatedSSE())
        _, current = await asyncio.gather(
            self.stream.unsubscribe(previous), self.stream.subscribe(),
        )
        await matching_message(current, connected=True)
        self.assertTrue(old_task.done())
        self.assertEqual(len(self.stream.clients), 1)
        readers = [task for task in asyncio.all_tasks() if task.get_name() == "hue-event-stream"]
        self.assertEqual(readers, [self.stream.task])


class WebSocketTests(unittest.TestCase):
    def test_two_websockets_receive_external_change_without_exposing_key(self):
        connection = SimulatedSSE()
        event_transport = SimulatedBridge(connection)
        rest_transport = HueTransport([resource(on=False)])
        bridge = HueBridgeV2("192.0.2.10", APP_KEY)
        bridge.create_request = event_transport.create_request
        bridge.request = AsyncMock(side_effect=rest_transport.request)
        bridge.close = AsyncMock()

        def connected_message(socket):
            for _ in range(3):
                message = socket.receive_json()
                if message["connected"]:
                    return message
            self.fail("WebSocket did not report a connected event stream")

        with (
            patch.object(main, "read_config", return_value=("192.0.2.10", APP_KEY)),
            patch.object(main, "HueBridgeV2", return_value=bridge),
            TestClient(main.app) as client,
        ):
            with client.websocket_connect("/api/ws") as first:
                connected_message(first)
                with client.websocket_connect("/api/ws") as second:
                    connected_message(second)
                    self.assertEqual(len(event_transport.calls), 1)

                    async def external_change():
                        rest_transport.resources[next(iter(rest_transport.resources))]["on"]["on"] = True
                        connection.event({"type": "light", "on": {"on": True}})

                    client.portal.call(external_change)
                    for socket in (first, second):
                        update = connected_message(socket)
                        self.assertEqual(update["type"], "bridge_update")
                        self.assertNotIn(APP_KEY, json.dumps(update))
                    self.assertTrue(client.get("/api/lights").json()[0]["on"])
                self.assertFalse(connection.closed.is_set())

            async def wait_for_reader_to_close():
                await asyncio.wait_for(connection.closed.wait(), timeout=2)

            client.portal.call(wait_for_reader_to_close)
        bridge.close.assert_awaited_once_with()

    def test_unconfigured_websocket_reports_setup_status_without_bridge_access(self):
        with (
            patch.object(main, "read_config", return_value=("", "")),
            patch.object(main, "HueBridgeV2") as constructor,
            TestClient(main.app) as client,
        ):
            with client.websocket_connect("/api/ws") as socket:
                message = socket.receive_json()
                self.assertEqual(message["type"], "bridge_update")
                self.assertFalse(message["configured"])
                self.assertFalse(message["connected"])
                self.assertEqual(message["bridge_ip"], "")
            constructor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
