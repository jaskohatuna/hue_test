"""One Hue SSE subscription shared by all browser WebSocket connections."""

import asyncio
import json

from aiohttp import ClientConnectionError, ClientError, ClientResponseError, ClientTimeout


def affects_lights(data: str) -> bool:
    """Hue events contain partial resources; use them only to invalidate a GET."""
    try:
        events = json.loads(data)
    except (ValueError, TypeError):
        return False
    if not isinstance(events, list):
        return False
    for event in events:
        if not isinstance(event, dict) or event.get("type") not in ("add", "update", "delete"):
            continue
        resources = event.get("data", [])
        if not isinstance(resources, list):
            continue
        if any(
            isinstance(item, dict)
            and item.get("type", item.get("rtype")) in ("light", "zigbee_connectivity", "device")
            for item in resources
        ):
            return True
    return False


class HueEventStream:
    def __init__(self, state):
        self.state = state
        self.clients: set[asyncio.Queue] = set()
        self.task: asyncio.Task | None = None
        self.lock = asyncio.Lock()
        self.connected = False
        self.detail = ""

    def message(self) -> dict:
        return {
            "type": "bridge_update",
            "connected": self.connected,
            "configured": self.state.bridge is not None,
            "bridge_ip": self.state.bridge_ip,
            "detail": self.detail,
        }

    def publish(self, connected: bool, detail: str = "") -> None:
        self.connected, self.detail = connected, detail
        for queue in self.clients:
            # A slow tab needs only the latest invalidation/status.
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(self.message())

    def start(self) -> None:
        if self.clients and self.state.bridge is not None and self.task is None:
            self.task = asyncio.create_task(self.run(), name="hue-event-stream")

    async def stop(self) -> None:
        if self.task is not None:
            task, self.task = self.task, None
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.connected = False

    async def subscribe(self) -> asyncio.Queue:
        async with self.lock:
            queue = asyncio.Queue(maxsize=1)
            self.clients.add(queue)
            queue.put_nowait(self.message())
            self.start()
            return queue

    async def unsubscribe(self, queue: asyncio.Queue) -> None:
        async with self.lock:
            self.clients.discard(queue)
            if not self.clients:
                await self.stop()

    async def restart(self) -> None:
        async with self.lock:
            await self.stop()
            self.publish(False)
            self.start()

    async def close(self) -> None:
        async with self.lock:
            await self.stop()
            self.clients.clear()

    async def run(self) -> None:
        last_event_id = ""
        retry = 1
        while True:
            bridge = self.state.bridge
            if bridge is None:
                return
            headers = {"Accept": "text/event-stream", "Cache-Control": "no-cache"}
            if last_event_id:
                headers["Last-Event-ID"] = last_event_id
            try:
                # Public aiohue transport supplies HTTPS and the application key.
                async with bridge.create_request(
                    "get", "eventstream/clip/v2", headers=headers,
                    timeout=ClientTimeout(total=None, sock_connect=8, sock_read=90),
                ) as response:
                    response.raise_for_status()
                    if not response.headers.get("Content-Type", "").startswith("text/event-stream"):
                        raise ClientConnectionError("Unexpected event stream response")
                    retry = 1
                    # Always resync after connecting, including after missed events.
                    self.publish(True)
                    data = []
                    data_size = 0
                    async for raw_line in response.content:
                        try:
                            line = raw_line.decode("utf-8").lstrip("\ufeff").rstrip("\r\n")
                        except UnicodeDecodeError:
                            continue
                        if not line:
                            if data_size <= 262144 and affects_lights("\n".join(data)):
                                self.publish(True)
                            data, data_size = [], 0
                            continue
                        field, separator, value = line.partition(":")
                        if not separator:
                            continue
                        value = value.removeprefix(" ")
                        if field == "id" and "\x00" not in value:
                            last_event_id = value
                        elif field == "data":
                            data_size += len(value)
                            if data_size <= 262144:
                                data.append(value)
                    raise ClientConnectionError("Event stream ended")
            except asyncio.CancelledError:
                raise
            except (ClientError, TimeoutError) as exc:
                if isinstance(exc, ClientResponseError) and exc.status in {401, 403}:
                    detail = "Bridge je odbio API ključ. Provjeri postavke Bridgea."
                elif isinstance(exc, ClientResponseError) and exc.status == 404:
                    detail = "Bridge ne podržava praćenje promjena kroz Hue API V2."
                else:
                    detail = "Veza za promjene je prekinuta. Pokušavam ponovo."
                self.publish(False, detail)
                await asyncio.sleep(retry)
                retry = min(retry * 2, 15)
