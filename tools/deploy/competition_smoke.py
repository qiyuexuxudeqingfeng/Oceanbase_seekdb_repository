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


def telemetry_matches(path, limit=80):
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    matches = [line for line in text.splitlines() if "telemetry" in line.lower()]
    return matches[-limit:]


def engine_telemetry_env(pid_file, proc_root=Path("/proc")):
    try:
        pid = pid_file.read_text(encoding="utf-8", errors="replace").strip()
    except OSError as error:
        return [], f"{pid_file}: {error}"
    if not pid.isdigit():
        return [], f"{pid_file}: invalid pid {pid!r}"
    environ_path = proc_root / pid / "environ"
    try:
        raw = environ_path.read_bytes()
    except OSError as error:
        return [], f"{environ_path}: {error}"
    entries = []
    status = f"pid {pid}: TELEMETRY_ENABLED absent"
    for entry in raw.decode("utf-8", "replace").split("\0"):
        name, separator, value = entry.partition("=")
        if separator and any(key in name for key in ("TELEMETRY", "REPORTER", "SEEKDB")):
            entries.append(entry)
            if name == "TELEMETRY_ENABLED":
                status = f"pid {pid}: TELEMETRY_ENABLED={value!r}"
    return entries, status


def telemetry_summary(path):
    if path is None:
        return "telemetry content unavailable: no telemetry.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        content = payload["content"]
        return (f"telemetry content: reporter={content.get('reporter')!r}, "
                f"telemetryVersion={content.get('telemetryVersion')!r}")
    except (OSError, json.JSONDecodeError, KeyError, TypeError, AttributeError) as error:
        return f"telemetry content unavailable: {error}"


def dump_diagnostics(candidates, database_path, proc_root=Path("/proc")):
    print("Telemetry delivery was not confirmed by the engine.", flush=True)
    for candidate in sorted(candidates):
        print(f"telemetry candidate {candidate}: exists={candidate.is_file()}", flush=True)
    entries, env_status = engine_telemetry_env(
        database_path / "run" / "seekdb.pid", proc_root)
    print(f"engine telemetry env: {env_status}", flush=True)
    for entry in entries:
        print(f"engine env {entry}", flush=True)
    state_path = next((p for p in sorted(candidates) if p.is_file()), None)
    print(telemetry_summary(state_path), flush=True)
    log_dir = database_path / "log"
    logs = sorted(p for p in log_dir.glob("*.log*") if p.is_file())[:4] if log_dir.is_dir() else []
    if not logs:
        names = sorted(p.name for p in log_dir.iterdir())[:20] if log_dir.is_dir() else []
        print(f"{log_dir}: exists={log_dir.is_dir()}, entries={names}", flush=True)
    for path in logs:
        matches = telemetry_matches(path)
        if matches is not None:
            print(f"--- {path}: {len(matches)} telemetry lines ---", flush=True)
            for line in matches:
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
