from __future__ import annotations

import tempfile
from pathlib import Path
from time import sleep

from virinda.application.service import AssistantService
from virinda.core.acceptance.models import AcceptanceResult, TurnAcceptanceRecord
from virinda.core.acceptance.probes import ResourceProbe
from virinda.core.events import InMemoryEventBus
from virinda.core.tokenizer import StreamingSentenceTokenizer
from virinda.core.trace import VoiceTurnResult
from virinda.core.voice import VoiceInteractionController
from virinda.core.voice_runtime import VoiceTurnRuntime
from virinda.domain.audio import AudioFrame, AudioPolicy, VoiceActivity
from virinda.infrastructure.persistence.sqlite import SQLiteConversationStore
from virinda.infrastructure.providers.echo import EchoProvider
from virinda.infrastructure.providers.router import StaticProviderRouter


def run_conversation_scenario(turns_count: int = 5) -> AcceptanceResult:
    res = AcceptanceResult(scenario="Scenario B: 5-Turn Continuous Conversation")
    res.resources_before = ResourceProbe.sample()

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "conversation.sqlite3"
        store = SQLiteConversationStore(db_path)
        bus = InMemoryEventBus()
        router = StaticProviderRouter({"echo": EchoProvider()}, default="echo")
        service = AssistantService(router=router, store=store, event_bus=bus)

        # Setup conversation turns
        conversation_script = [
            ("What is the capital of France?", "Paris"),
            ("What is the highest mountain in the world?", "Everest"),
            ("Tell me a fact about oceans.", "oceans"),
            ("How many planets are in our solar system?", "planets"),
            ("What is the chemical formula for water?", "H2O"),
        ]

        class MultiTurnRecognizer:
            def __init__(self):
                self.index = 0

            def transcribe(self, frames):
                utterance = conversation_script[self.index % len(conversation_script)][0]
                self.index += 1
                return utterance

        class MultiTurnTTS:
            def synthesize(self, text):
                return [AudioFrame(b"conversation_audio")]

        class MultiTurnOutput:
            def play_interruptible(self, frames, *, cancel_event):
                for _ in range(2):
                    if cancel_event.is_set():
                        return
                    sleep(0.005)

            def stop(self):
                pass

        results: list[VoiceTurnResult] = []
        controller = VoiceInteractionController(
            policy=AudioPolicy(min_speech_ms=0, end_silence_ms=0),
            vad=VoiceActivity(True),
        )

        class MultiTurnVad:
            def reset(self):
                pass

            def process(self, frame):
                return VoiceActivity(True)

        controller.vad = MultiTurnVad()

        runtime = VoiceTurnRuntime(
            service=service,
            controller=controller,
            recognizer=MultiTurnRecognizer(),
            synthesizer=MultiTurnTTS(),
            output=MultiTurnOutput(),
            tokenizer=StreamingSentenceTokenizer(),
            on_turn_result=results.append,
        )

        for i in range(turns_count):
            controller.arm()
            controller.trigger_listening("wake_word")
            controller.on_audio(AudioFrame(b"pcm_frame"), now=0.0)
            controller.push_to_talk_released()

            for _ in range(200):
                if len(results) > i:
                    break
                sleep(0.01)

        # Assertion 1: All 5 turns completed
        res.add_assertion(
            "all_turns_completed",
            len(results) == turns_count,
            expected=turns_count,
            actual=len(results),
        )

        # Assertion 2: 5 unique correlation UUIDs
        unique_ids = {r.trace.interaction_id for r in results}
        res.add_assertion(
            "unique_correlation_ids",
            len(unique_ids) == len(results),
            expected=len(results),
            actual=len(unique_ids),
        )

        # Assertion 3: Check latencies and drift
        latencies = [
            r.metrics.total_interaction_ms
            for r in results
            if r.metrics.total_interaction_ms is not None
        ]
        res.add_assertion(
            "latencies_measured",
            len(latencies) == len(results),
            expected=len(results),
            actual=len(latencies),
        )

        for idx, r in enumerate(results):
            record = TurnAcceptanceRecord(
                index=idx + 1,
                utterance=r.transcript,
                response=r.response,
                correlation_id=r.trace.interaction_id,
                interrupted=r.interrupted,
                latency=r.metrics,
                passed=not r.interrupted and bool(r.response),
            )
            res.records.append(record)

        # Calculate latency slope / drift (last turn latency vs first turn latency)
        if len(latencies) >= 2:
            drift = latencies[-1] - latencies[0]
            res.add_assertion(
                "latency_drift_bounded",
                drift < 2000.0,  # Max drift under 2 seconds across 5 turns
                expected="< 2000ms drift",
                actual=f"{drift:.2f}ms",
            )

        # Assertion 4: Conversation messages persisted in database
        session_id = service.snapshot().session_id
        persisted_messages = store.load_messages(session_id)
        res.add_assertion(
            "messages_persisted",
            len(persisted_messages) == turns_count * 2,  # User + assistant message per turn
            expected=turns_count * 2,
            actual=len(persisted_messages),
        )

        runtime.close()
        service.close()

    res.resources_after = ResourceProbe.sample()
    res.finalize()
    return res
