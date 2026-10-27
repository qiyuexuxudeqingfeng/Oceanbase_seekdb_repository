#!/usr/bin/env python3

import asyncio
import json
import os
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
        return candidate, identifier, payload.get("sent")
    return None


def log_tail(path, lines=80):
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    return text.splitlines()[-lines:]


def dump_diagnostics(candidates, database_path):
    print("Telemetry delivery was not confirmed by the engine.", flush=True)
    for candidate in sorted(candidates):
        print(f"telemetry candidate {candidate}: exists={candidate.is_file()}", flush=True)
    log_dir = database_path / "log"
    logs = sorted(p for p in log_dir.glob("*.log*") if p.is_file())[:4] if log_dir.is_dir() else []
    if not logs:
        entries = sorted(p.name for p in log_dir.iterdir())[:20] if log_dir.is_dir() else []
        print(f"{log_dir}: exists={log_dir.is_dir()}, entries={entries}", flush=True)
    for path in logs:
        tail = log_tail(path)
        if tail is not None:
            print(f"--- {path} (last {len(tail)} lines) ---", flush=True)
            for line in tail:
                print(line, flush=True)


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
        last_state = None
        while True:
            state = telemetry_state(candidates)
            if state is not None and state != last_state:
                path, identifier, sent = state
                print(f"telemetry {path}: sent={sent!r}, uuid={identifier}", flush=True)
                last_state = state
            if state is not None and state[2] is True:
                identifier = state[1]
                print(f"DEPLOYMENT_UUID={identifier}", flush=True)
                print("Telemetry delivery confirmed by the engine.", flush=True)
                output_path = os.environ.get("GITHUB_OUTPUT")
                if output_path:
                    with Path(output_path).open("a", encoding="utf-8") as output:
                        output.write(f"deployment_uuid={identifier}\n")
                return
            if time.monotonic() >= deadline:
                dump_diagnostics(candidates, database_path)
                raise RuntimeError(
                    "The engine did not confirm telemetry delivery within 120 seconds"
                )
            time.sleep(2)
    finally:
        instance.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: competition_smoke.py DATABASE_PATH")
    asyncio.run(main())
