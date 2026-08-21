# Testing and Verification

Virinda uses several test layers because no single test can prove the whole desktop voice stack.

## Layer 1 — unit and application tests

```bash
python -m pytest -q
```

This covers state transitions, cancellation, persistence, memory, feature policy, security, IPC, OVOS adapters, and deterministic provider behavior.

## Layer 2 — source/release validation

```bash
./scripts/check.sh
./scripts/validate-release.sh
python scripts/verify-ovos-compatibility.py
```

These validate compilation, release metadata, compatibility constraints, configuration, and package hygiene.

## Layer 3 — package verification

Build the wheel without network dependency on an already provisioned build environment:

```bash
python -m pip wheel . --no-build-isolation --no-deps -w dist
```

Verify wheel metadata contains the same version as `src/virinda/__init__.py`.

## Layer 4 — OVOS environment smoke

The environment smoke test validates package installation and selected profile requirements:

```bash
python scripts/ovos-smoke.py --profile stable
python scripts/ovos-smoke.py --profile local-voice
```

This does **not** prove that the message bus or hardware works.

## Layer 5 — live OVOS application smoke

```bash
python scripts/ovos-runtime-smoke.py \
  "virinda status" \
  --expect "Virinda is online"
```

This validates the application message path:

`MessageBus → ovos-core → Virinda skill → response`

## Layer 6 — live voice acceptance

On a provisioned Linux desktop:

1. Start `virinda-voice.target`.
2. Verify the listener is healthy.
3. Verify the selected microphone.
4. Trigger the configured wake model.
5. Speak a deterministic command.
6. Verify the transcript event.
7. Verify the Virinda response event.
8. Verify audio output.
9. Interrupt speech and verify barge-in/cancellation.
10. Repeat in private/quiet/focus modes.

This layer requires actual hardware and should be reported separately from CI.

## Layer 7 — performance benchmark

Record:

- wake detection latency
- speech-end detection latency
- STT first/final token latency
- provider first token latency
- TTS first-audio latency
- total turn latency
- barge-in latency
- dropped/cancelled turn count

Use the `VoiceBenchmark` storage and `docs/PERFORMANCE.md` protocol.

## Test philosophy

Prefer deterministic local tests. External providers should be exercised with local HTTP fixtures or contract doubles. OVOS should be integration-tested as a pinned environment. Hardware checks should never be faked with mocks and presented as real device validation.


## Job broker testing

All background job behavior must be testable with the in-process broker before a real broker is introduced. The test matrix should cover:

1. publish/consume ordering where ordering is part of the contract;
2. duplicate delivery/idempotency;
3. retry/backoff;
4. approval-required jobs;
5. cancellation/expiry;
6. dead-letter behavior;
7. broker-unavailable behavior;
8. NATS adapter conformance against the same contract tests.

The OVOS MessageBus test path remains separate because realtime/interactive behavior has different failure and latency requirements.


## Rust audio-core validation

The `rust/audio-core` crate is intentionally small and dependency-free. On a machine with the Rust toolchain installed, run `cargo test --manifest-path rust/audio-core/Cargo.toml`. The generation controller tests verify monotonic starts, interruption invalidation, and concurrent update uniqueness. The current development environment does not include `cargo`/`rustc`, so repository-level validation must report native Rust compilation as pending rather than passing.

Voice runtime tests additionally cover stale STT/TTS workers: cancellation must prevent late recognition from calling `AssistantService.ask()` and late synthesized audio from reaching `AudioOutput.play()`.
They also cover in-progress interruptible playback and verify that each TTS worker has an independent cancellation event, preventing a later turn from accidentally re-enabling an older playback worker.
