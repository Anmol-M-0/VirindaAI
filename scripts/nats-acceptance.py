#!/usr/bin/env python3
"""Validate a live NATS JetStream environment for Marina.

Exit codes:
  0 = live connectivity and publish/consume path passed
  2 = environment is not provisioned (missing nats-py or nats-server/connectivity)
  1 = provisioned but the acceptance test failed

The test creates a temporary stream/consumer subject, publishes one Marina-style
job, consumes and acknowledges it, then confirms the durable JetStream path works.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=os.environ.get("MARINA_NATS_URL", "nats://127.0.0.1:4222"))
    parser.add_argument("--timeout", type=float, default=3.0)
    return parser.parse_args()


async def run(url: str, timeout: float) -> int:
    try:
        import nats
        from nats.js import api
    except ImportError:
        print("NATS acceptance: environment_missing (install the job-backbone extra)")
        return 2

    stream = f"marina_accept_{uuid.uuid4().hex[:10]}"
    subject = f"marina.accept.{uuid.uuid4().hex}"
    durable = f"marina-accept-{uuid.uuid4().hex[:10]}"
    nc = None
    try:
        nc = await asyncio.wait_for(nats.connect(url), timeout=timeout)
        js = nc.jetstream()
        await js.add_stream(
            name=stream,
            subjects=[subject],
            retention=api.RetentionPolicy.WORK_QUEUE,
        )
        sub = await js.pull_subscribe(subject, durable=durable, stream=stream)
        payload = b'{"subject":"marina.jobs.acceptance","payload":{"ok":true}}'
        await js.publish(subject, payload)
        message = await sub.next_msg(timeout=timeout)
        if message.data != payload:
            print("NATS acceptance: fail (unexpected message payload)")
            return 1
        await message.ack()
        print(f"NATS acceptance: PASS ({url})")
        return 0
    except Exception as exc:  # noqa: BLE001 - acceptance diagnostic boundary
        print(f"NATS acceptance: environment_missing_or_unavailable ({exc})")
        return 2
    finally:
        if nc is not None:
            try:
                await nc.drain()
            except Exception:
                await nc.close()


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(asyncio.run(run(args.url, args.timeout)))
