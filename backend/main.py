"""Small local Hue API for the mobile app.

Start with: python -m uvicorn main:app --host 0.0.0.0 --port 8000
"""

import asyncio
from contextlib import asynccontextmanager
from ipaddress import ip_address
from uuid import UUID

from aiohttp import ClientError, ClientResponseError
from aiohue import HueBridgeV2, create_app_key
from aiohue.errors import AiohueException, LinkButtonNotPressed, Unauthorized
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import (
    BaseModel, ConfigDict, Field, SecretStr, StrictBool, field_validator, model_validator,
)

from config import APP_ORIGINS, bridge_host, read_config, write_config
from realtime import HueEventStream

BRIDGE_TIMEOUT = 8
PAIRING_TIMEOUT = 15


@asynccontextmanager
async def lifespan(app: FastAPI):
    ip, key = read_config()
    app.state.bridge_lock = asyncio.Lock()
    app.state.bridge_ip = ip
    app.state.bridge = None
    app.state.config_error = "Poveži Bridge kroz postavke na ovoj stranici."
    if ip and key:
        try:
            host = bridge_host(ip)
        except ValueError:
            app.state.config_error = "IP adresa nije ispravna. Poveži Bridge kroz postavke."
        else:
            # request() opens the aiohttp session lazily.
            app.state.bridge = HueBridgeV2(host, key)
    app.state.realtime = HueEventStream(app.state)
    try:
        yield
    finally:
        await app.state.realtime.close()
        if app.state.bridge is not None:
            await app.state.bridge.close()


app = FastAPI(title="Lokalna Hue svjetla", lifespan=lifespan)
# The app is served from its own origin (WebView or Vite), not from this server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(APP_ORIGINS),
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
    max_age=600,
)


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, _error: RequestValidationError):
    # Validation errors normally include the submitted input; never echo a key.
    detail = (
        "Unesi ispravnu IP adresu i API ključ ili odaberi povezivanje dugmetom na Bridgeu."
        if request.url.path == "/api/setup"
        else "Zahtjev nije ispravan. Pošalji on (true/false) i/ili brightness (1–100)."
    )
    return JSONResponse(status_code=422, content={"detail": detail}, headers={"Cache-Control": "no-store"})


class SetupStatus(BaseModel):
    bridge_ip: str
    configured: bool


class SetupCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bridge_ip: str = Field(min_length=1, max_length=64)
    app_key: SecretStr | None = Field(default=None, max_length=256)

    @field_validator("bridge_ip")
    @classmethod
    def valid_ip(cls, value: str) -> str:
        return str(ip_address(value.strip()))

    @field_validator("app_key")
    @classmethod
    def valid_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        key = value.get_secret_value().strip()
        if any(character.isspace() or not character.isprintable() for character in key):
            raise ValueError("Invalid key")
        return SecretStr(key) if key else None


class Light(BaseModel):
    id: str
    name: str
    on: bool
    # Percent (Hue V2 "dimming"); omitted for lights that cannot be dimmed.
    brightness: float | None = None
    available: bool | None = None


class LightCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    on: StrictBool | None = None
    # The Bridge treats 0 as its lowest level, so turning off is only done with on=false.
    brightness: float | None = Field(default=None, ge=1, le=100, strict=True)

    @model_validator(mode="after")
    def has_change(self):
        if self.on is None and self.brightness is None:
            raise ValueError("Empty command")
        return self


def get_bridge(request: Request) -> HueBridgeV2:
    if request.app.state.bridge is None:
        raise HTTPException(status_code=503, detail=request.app.state.config_error)
    return request.app.state.bridge


@asynccontextmanager
async def bridge_operation(
    timeout: float | None = None, missing_message: str = "Svjetlo nije pronađeno."
):
    """Bound aiohue's retries and return short errors without exposing secrets."""
    try:
        async with asyncio.timeout(BRIDGE_TIMEOUT if timeout is None else timeout):
            yield
    except LinkButtonNotPressed:
        raise HTTPException(
            status_code=400,
            detail="Pritisni fizičko dugme na Bridgeu pa odmah ponovo klikni Poveži Bridge.",
        ) from None
    except Unauthorized:
        raise HTTPException(
            status_code=503,
            detail="Bridge je odbio API ključ. Otvori postavke i poveži Bridge ponovo.",
        ) from None
    except ClientResponseError as exc:
        if exc.status == 404:
            raise HTTPException(status_code=404, detail=missing_message) from None
        raise HTTPException(
            status_code=503,
            detail="Bridge nije dostupan. Provjeri IP adresu i mrežnu vezu.",
        ) from None
    except (ClientError, TimeoutError):
        raise HTTPException(
            status_code=503,
            detail="Bridge nije dostupan. Provjeri IP adresu i mrežnu vezu.",
        ) from None
    except AiohueException:
        raise HTTPException(
            status_code=502,
            detail="Bridge nije mogao izvršiti zahtjev. Pokušaj ponovo.",
        ) from None


def setup_status(request: Request) -> SetupStatus:
    return SetupStatus(
        bridge_ip=request.app.state.bridge_ip,
        configured=request.app.state.bridge is not None,
    )


@app.get("/api/setup", response_model=SetupStatus)
async def get_setup(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return setup_status(request)


@app.post("/api/setup", response_model=SetupStatus)
async def connect_bridge(command: SetupCommand, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    async with request.app.state.bridge_lock:
        host = bridge_host(command.bridge_ip)
        key = command.app_key.get_secret_value() if command.app_key else None
        if not key:
            async with bridge_operation(
                PAIRING_TIMEOUT, "Na ovoj IP adresi nije dostupan kompatibilan Hue Bridge."
            ):
                key = await create_app_key(host, "local-hue#mobile")

        candidate = HueBridgeV2(host, key)
        try:
            # Check credentials and connectivity before changing the saved config.
            async with bridge_operation(
                missing_message="Na ovoj IP adresi nije dostupan Hue Bridge s API V2."
            ):
                await candidate.request("get", "clip/v2/resource/light")
            try:
                write_config(command.bridge_ip, key)
            except OSError:
                raise HTTPException(
                    status_code=500,
                    detail="Postavke nije moguće sačuvati. Provjeri dozvolu pisanja u backend folder.",
                ) from None
        except BaseException:
            await candidate.close()
            raise

        previous = request.app.state.bridge
        request.app.state.bridge = candidate
        request.app.state.bridge_ip = command.bridge_ip
        # Cancel and await the old reader before closing its HTTP session.
        await request.app.state.realtime.restart()
        if previous is not None:
            await previous.close()
        return setup_status(request)


def light_response(resource: dict, connectivity: list[dict]) -> Light:
    owner = resource.get("owner", {}).get("rid")
    status = next(
        (item.get("status") for item in connectivity if item.get("owner", {}).get("rid") == owner),
        None,
    )
    available = True if status == "connected" else (
        False if status in {"disconnected", "connectivity_issue"} else None
    )
    return Light(
        id=resource["id"],
        name=resource["metadata"]["name"],
        on=resource["on"]["on"],
        brightness=(resource.get("dimming") or {}).get("brightness"),
        available=available,
    )


@app.get("/api/lights", response_model=list[Light], response_model_exclude_none=True)
async def list_lights(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    async with request.app.state.bridge_lock:
        bridge = get_bridge(request)
        async with bridge_operation():
            # Always fetch from the Bridge, never return the controller's cache.
            resources = await bridge.request("get", "clip/v2/resource/light")
            connectivity = await bridge.request("get", "clip/v2/resource/zigbee_connectivity")
    return sorted(
        (light_response(resource, connectivity) for resource in resources),
        key=lambda light: light.name.casefold(),
    )


@app.put("/api/lights/{light_id}", response_model=Light, response_model_exclude_none=True)
async def set_light(light_id: UUID, command: LightCommand, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    resource_id = str(light_id)
    async with request.app.state.bridge_lock:
        bridge = get_bridge(request)
        async with bridge_operation():
            await bridge.lights.set_state(resource_id, on=command.on, brightness=command.brightness)
            # A PUT acknowledgement is not a state snapshot: explicitly read it back.
            resources = await bridge.request("get", f"clip/v2/resource/light/{resource_id}")
            connectivity = await bridge.request("get", "clip/v2/resource/zigbee_connectivity")
    if not resources:
        raise HTTPException(status_code=404, detail="Svjetlo nije pronađeno.")
    return light_response(resources[0], connectivity)


@app.websocket("/api/ws")
async def light_events(websocket: WebSocket):
    await websocket.accept()
    stream = websocket.app.state.realtime
    queue = await stream.subscribe()

    async def send_updates():
        while True:
            await websocket.send_json(await queue.get())

    async def receive_until_disconnect():
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return

    tasks = [asyncio.create_task(send_updates()), asyncio.create_task(receive_until_disconnect())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await stream.unsubscribe(queue)
