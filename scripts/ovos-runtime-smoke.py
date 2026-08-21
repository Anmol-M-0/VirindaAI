#!/usr/bin/env python3
"""Exercise the live OVOS message-bus/core path without microphone hardware.

Requires a provisioned OVOS environment with ovos-messagebus and ovos-core running.
The probe injects an utterance through the same ``recognizer_loop:utterance`` bus
entry used by the listener, then waits for a ``speak`` response from the pipeline.
"""
from __future__ import annotations

import argparse
import json
import sys
import shutil
import subprocess
import time
from threading import Event


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("utterance", nargs="?", default="marina status")
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--expect", default="")
    parser.add_argument("--stage", choices=("core", "voice", "custom"), default="core", help="Acceptance stage; core checks bus/core, voice checks listener/audio too")
    parser.add_argument("--require-services", action="store_true", help="Require OVOS user services to be active before probing the bus")
    parser.add_argument("--services", nargs="*", default=[], help="User services to require when --require-services is used")
    args = parser.parse_args()

    try:
        from ovos_bus_client import Message, MessageBusClient
    except ImportError as exc:
        print(json.dumps({"ok": False, "status": "environment_missing", "detail": str(exc)}))
        return 2

    preset_services = {
        "core": ["marina-messagebus.service", "marina-core.service"],
        "voice": ["marina-messagebus.service", "marina-core.service", "marina-listener.service", "marina-audio.service"],
    }
    required_services = list(args.services) if args.services else preset_services.get(args.stage, [])

    if args.require_services:
        systemctl = shutil.which("systemctl")
        if not systemctl:
            print(json.dumps({"ok": False, "status": "environment_missing", "detail": "systemctl is unavailable"}))
            return 2
        service_states = {}
        for unit in required_services:
            try:
                result = subprocess.run(
                    [systemctl, "--user", "is-active", unit],
                    capture_output=True, text=True, timeout=3, check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                print(json.dumps({"ok": False, "status": "service_probe_failed", "unit": unit, "detail": str(exc)}))
                return 2
            state = result.stdout.strip() or result.stderr.strip() or "unknown"
            service_states[unit] = state
            if state != "active":
                print(json.dumps({"ok": False, "status": "services_not_ready", "services": service_states}, indent=2))
                return 2

    started_at = time.monotonic()
    done = Event()
    responses: list[str] = []
    client = MessageBusClient()

    def on_speak(message) -> None:  # OVOS Message type is optional at source-build time.
        utterance = str(getattr(message, "data", {}).get("utterance", "")).strip()
        if utterance:
            responses.append(utterance)
            done.set()

    try:
        client.on("speak", on_speak)
        client.run_in_thread()
        if not client.connected_event.wait(timeout=args.timeout):
            print(json.dumps({"ok": False, "status": "bus_unavailable", "detail": "message bus did not connect"}))
            return 2
        client.emit(
            Message(
                "recognizer_loop:utterance",
                {"utterances": [args.utterance], "lang": "en-us"},
            )
        )
        if not done.wait(timeout=args.timeout):
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "pipeline_timeout",
                        "utterance": args.utterance,
                        "responses": responses,
                    }
                )
            )
            return 1
        matched = not args.expect or any(args.expect.lower() in r.lower() for r in responses)
        payload = {
            "ok": matched,
            "stage": args.stage,
            "services_required": args.require_services,
            "services": service_states if args.require_services else {},
            "status": "passed" if matched else "unexpected_response",
            "utterance": args.utterance,
            "responses": responses,
            "elapsed_ms": round((time.monotonic() - started_at) * 1000, 2),
        }
        print(json.dumps(payload, indent=2))
        return 0 if matched else 1
    finally:
        try:
            client.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
