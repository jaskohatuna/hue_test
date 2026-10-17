"""Print a new Hue application key for manual copying into backend/.env."""

import asyncio

from aiohttp import ClientError
from aiohue import create_app_key
from aiohue.errors import AiohueException, LinkButtonNotPressed

from config import bridge_host, read_config


async def register(host: str) -> str:
    async with asyncio.timeout(15):
        return await create_app_key(host, "local-hue#desktop")


def main() -> int:
    ip, _ = read_config()
    try:
        host = bridge_host(ip)
    except ValueError:
        print("Upiši ispravnu HUE_BRIDGE_IP adresu u backend/.env.")
        return 1

    input("Pritisni dugme na Hue Bridgeu, pa odmah pritisni Enter ovdje...")
    try:
        key = asyncio.run(register(host))
    except LinkButtonNotPressed:
        print("Bridge dugme nije pritisnuto ili je vrijeme isteklo. Pritisni ga i pokreni skriptu ponovo.")
        return 1
    except (ClientError, TimeoutError):
        print("Bridge nije dostupan. Provjeri HUE_BRIDGE_IP i mrežnu vezu.")
        return 1
    except AiohueException:
        print("Bridge nije odobrio povezivanje. Pokušaj ponovo.")
        return 1

    print("Ručno kopiraj sljedeći red u backend/.env (skripta ne mijenja datoteku):")
    print(f"HUE_APP_KEY={key}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt, EOFError):
        print("\nPovezivanje je prekinuto.")
        raise SystemExit(1)
