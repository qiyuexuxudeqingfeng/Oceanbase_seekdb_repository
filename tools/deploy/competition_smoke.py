#!/usr/bin/env python3

import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

import pymysql
import pylibseekdb


def telemetry_state(candidates):
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            identifier = payload["content"]["id"]
            parsed = uuid.UUID(identifier)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
        if str(parsed) != identifier:
            continue
        return identifier, payload.get("sent")
    return None


async def main():
    database_path = Path(sys.argv[1]).resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    instance = await pylibseekdb.aopen(str(database_path))
    try:
        options = dict(instance.connection_options())
        options.setdefault("database", "test")
        with pymysql.connect(**options) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                row = cursor.fetchone()
        if row != (1,):
            raise RuntimeError(f"Unexpected SQL smoke-check result: {row!r}")
        print("SQL smoke check passed: SELECT 1 -> 1", flush=True)

        candidates = {
            database_path / "run" / "telemetry.json",
            database_path.parent / "run" / "telemetry.json",
            Path.cwd() / "run" / "telemetry.json",
        }
        deadline = time.monotonic() + 120
        while True:
            state = telemetry_state(candidates)
            if state is not None and state[1] is not False:
                print(f"DEPLOYMENT_UUID={state[0]}", flush=True)
                if state[1] is True:
                    print("Telemetry delivery confirmed by the engine.", flush=True)
                return
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "The engine did not produce a delivered telemetry ID within 120 seconds"
                )
            time.sleep(2)
    finally:
        instance.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: competition_smoke.py DATABASE_PATH")
    asyncio.run(main())
