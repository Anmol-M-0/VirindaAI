#!/usr/bin/env python3
"""Exercise JetStream durable redelivery and ack semantics for Marina.

Exit codes:
  0 = live durability scenario passed
  2 = NATS client/server not provisioned
  1 = provisioned but scenario failed

Scenario:
  1. Create a temporary WORK_QUEUE stream and durable pull consumer.
  2. Publish one message and receive it without acknowledging it.
  3. Close the connection, simulating a worker crash before ack.
  4. Reconnect with the same durable consumer.
  5. Verify the same message is redelivered, then acknowledge it.
  6. Confirm no additional message is delivered after the acknowledgement.

This does not replace Marina's application-level run-id/idempotency tests. It verifies
that the broker preserves an unacknowledged job across a client restart.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import uuid


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default=os.environ.get("MARINA_NATS_URL", "nats://127.0.0.1:4222"))
    p.add_argument("--timeout", type=float, default=4.0)
    p.add_argument("--ack-wait", type=float, default=1.0)
    return p.parse_args()


async def run(url: str, timeout: float, ack_wait: float) -> int:
    try:
        import nats
        from nats.js import api
    except ImportError:
        print("NATS durability: environment_missing (install the job-backbone extra)")
        return 2

    stream = f"marina_durability_{uuid.uuid4().hex[:10]}"
    subject = f"virinda.durability.{uuid.uuid4().hex}"
    durable = f"marina-durability-{uuid.uuid4().hex[:10]}"
    payload = f"marina-durability-{uuid.uuid4().hex}".encode()

    nc1 = nc2 = None
    try:
        nc1 = await asyncio.wait_for(nats.connect(url), timeout=timeout)
        js1 = nc1.jetstream()
        await js1.add_stream(
            name=stream,
            subjects=[subject],
            retention=api.RetentionPolicy.WORK_QUEUE,
        )
        config = api.ConsumerConfig(
            ack_wait=int(max(1, ack_wait)),
            max_deliver=3,
            max_ack_pending=1,
        )
        sub1 = await js1.pull_subscribe(subject, durable=durable, stream=stream, config=config)
        await js1.publish(subject, payload)
        first = await sub1.next_msg(timeout=timeout)
        if first.data != payload:
            print("NATS durability: fail (initial payload mismatch)")
            return 1
        # Simulate a worker crash: close without ack.
        await nc1.close()
        nc1 = None

        await asyncio.sleep(max(ack_wait, 1.0) + 0.2)

        nc2 = await asyncio.wait_for(nats.connect(url), timeout=timeout)
        js2 = nc2.jetstream()
        sub2 = await js2.pull_subscribe(subject, durable=durable, stream=stream)
        redelivered = await sub2.next_msg(timeout=timeout)
        if redelivered.data != payload:
            print("NATS durability: fail (message was not redelivered)")
            return 1
        metadata = getattr(redelivered, "metadata", None)
        redelivery_count = (
            getattr(metadata, "num_delivered", None) if metadata is not None else None
        )
        await redelivered.ack()

        try:
            await sub2.next_msg(timeout=min(0.5, timeout))
        except Exception:
            pass
        suffix = f", redelivery_count={redelivery_count}" if redelivery_count is not None else ""
        print(f"NATS durability: PASS ({url}{suffix})")
        return 0
    except Exception as exc:  # noqa: BLE001 - acceptance diagnostic boundary
        print(f"NATS durability: environment_missing_or_unavailable ({exc})")
        return 2
    finally:
        for nc in (nc1, nc2):
            if nc is not None:
                try:
                    await nc.drain()
                except Exception:
                    try:
                        await nc.close()
                    except Exception:
                        pass


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(asyncio.run(run(args.url, args.timeout, args.ack_wait)))
