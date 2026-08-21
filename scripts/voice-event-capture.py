#!/usr/bin/env python3
"""Capture normalized OVOS voice lifecycle events as JSONL.

This is a hardware acceptance utility, not a second voice pipeline. It subscribes
passively to the local OVOS MessageBus and writes timestamps only; no PCM audio or
transcripts are persisted by this utility.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4

EVENT_MAP = {
    "ovos.listener.wakeword": "wake.detected",
    "ovos.listener.record.started": "record.started",
    "ovos.listener.record.ended": "record.ended",
    "recognizer_loop:utterance": "stt.completed",
    "ovos.audio.output.started": "audio.output.started",
    "ovos.audio.output.ended": "audio.output.ended",
    "mycroft.stop": "barge_in.requested",
}

def correlate_event(
    event: str,
    *,
    current_turn: str | None,
    output_turn: str | None,
    new_turn_id: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Return ``(event_turn, current_turn, output_turn)`` for one normalized event.

    Output completion belongs to the turn whose playback started, even when a new
    recording begins before the asynchronous output-stop event arrives.
    """
    if event == "wake.detected":
        # Do not let duplicate/late wake events replace an already-active turn.
        # When wake arrives during playback, create the new barge-in turn now;
        # the subsequent record.started event must preserve this same turn.
        if current_turn is None or current_turn == output_turn:
            current_turn = new_turn_id or current_turn
        return current_turn, current_turn, output_turn
    if event == "record.started":
        # A recording that begins while previous TTS is still active is a new
        # barge-in turn only when no wake-correlated turn already exists.
        if output_turn is not None and current_turn == output_turn:
            current_turn = new_turn_id
        else:
            current_turn = current_turn or new_turn_id
        return current_turn, current_turn, output_turn
    if event == "audio.output.started":
        output_turn = current_turn
        return output_turn, current_turn, output_turn
    if event == "audio.output.ended":
        completed_turn = output_turn or current_turn
        if completed_turn == output_turn:
            output_turn = None
        if completed_turn == current_turn:
            current_turn = None
        return completed_turn, current_turn, output_turn
    return current_turn, current_turn, output_turn



def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=60.0, help="capture window in seconds")
    parser.add_argument("--output", type=str, default="-", help="JSONL output path, or - for stdout")
    args = parser.parse_args()
    try:
        from ovos_bus_client import MessageBusClient
    except ImportError as exc:  # pragma: no cover - exercised on machines without OVOS
        print("OVOS bus client is unavailable; install marina-ai[ovos]", file=sys.stderr)
        return 2

    output = sys.stdout if args.output == "-" else open(args.output, "w", encoding="utf-8")
    client = MessageBusClient()
    current_turn: str | None = None
    output_turn: str | None = None

    def emit(event: str, *, turn_id: str | None = None) -> None:
        row = {
            "turn_id": current_turn if turn_id is None else turn_id,
            "event": event,
            "timestamp": time.time(),
            "timestamp_iso": datetime.now(timezone.utc).isoformat(),
        }
        output.write(json.dumps(row, separators=(",", ":")) + "\n")
        output.flush()

    def handler(message) -> None:
        nonlocal current_turn, output_turn
        event = EVENT_MAP.get(message.msg_type)
        if event is None:
            return
        new_turn_id = uuid4().hex if event == "record.started" else None
        event_turn, current_turn, output_turn = correlate_event(
            event,
            current_turn=current_turn,
            output_turn=output_turn,
            new_turn_id=new_turn_id,
        )
        emit(event, turn_id=event_turn)

    for message_type in EVENT_MAP:
        client.on(message_type, handler)

    client.run_in_thread()
    if not client.connected_event.wait(timeout=5):
        print("OVOS messagebus connection timed out", file=sys.stderr)
        if output is not sys.stdout:
            output.close()
        return 2

    print(f"capturing OVOS voice events for {args.duration:.1f}s", file=sys.stderr)
    deadline = time.monotonic() + max(0.1, args.duration)
    try:
        while time.monotonic() < deadline:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        client.close()
        if output is not sys.stdout:
            output.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
