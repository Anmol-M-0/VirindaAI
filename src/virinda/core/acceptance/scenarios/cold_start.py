from __future__ import annotations

import tempfile
from pathlib import Path
from time import sleep
from uuid import UUID

from virinda.application.service import AssistantService
from virinda.core.acceptance.models import AcceptanceResult
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


def run_cold_start_scenario(data_dir: Path | None = None) -> AcceptanceResult:
    res = AcceptanceResult(scenario="Scenario A: Cold Start User Journey")
    res.resources_before = ResourceProbe.sample()

    with tempfile.TemporaryDirectory() as tmp_dir:
        target_dir = data_dir or Path(tmp_dir)
        db_path = target_dir / "virinda_cold_start.sqlite3"

        # Assertion 1: Clean DB does not exist before start
        res.add_assertion(
            "clean_start_no_preexisting_db",
            not db_path.exists(),
            expected=True,
            actual=not db_path.exists(),
        )

        store = SQLiteConversationStore(db_path)
        bus = InMemoryEventBus()
        router = StaticProviderRouter({"echo": EchoProvider()}, default="echo")
        service = AssistantService(router=router, store=store, event_bus=bus)

        # Assertion 2: DB created and accessible
        res.add_assertion(
            "database_initialized",
            db_path.exists(),
            expected=True,
            actual=db_path.exists(),
        )

        class ColdStartVad:
            def reset(self):
                pass

            def process(self, frame):
                return VoiceActivity(True)

        class ColdStartRecognizer:
            def transcribe(self, frames):
                return "What is the capital of France?"

        class ColdStartTTS:
            def synthesize(self, text):
                return [AudioFrame(b"paris_audio")]

        class ColdStartOutput:
            def __init__(self):
                self.played = False

            def play_interruptible(self, frames, *, cancel_event):
                self.played = True

            def stop(self):
                pass

        output = ColdStartOutput()
        results: list[VoiceTurnResult] = []
        controller = VoiceInteractionController(
            policy=AudioPolicy(min_speech_ms=0, end_silence_ms=0),
            vad=ColdStartVad(),
        )
        runtime = VoiceTurnRuntime(
            service=service,
            controller=controller,
            recognizer=ColdStartRecognizer(),
            synthesizer=ColdStartTTS(),
            output=output,
            tokenizer=StreamingSentenceTokenizer(),
            on_turn_result=results.append,
        )

        # Execute first turn
        controller.arm()
        controller.trigger_listening("wake_word")
        controller.on_audio(AudioFrame(b"pcm_frame"), now=0.0)
        controller.push_to_talk_released()

        for _ in range(50):
            if results:
                break
            sleep(0.01)

        # Assertion 3: First turn produced exactly 1 result
        res.add_assertion(
            "first_turn_completed",
            len(results) == 1,
            expected=1,
            actual=len(results),
        )

        if results:
            result = results[0]
            # Assertion 4: Response generated correctly
            res.add_assertion(
                "response_generated",
                "Virinda received: What is the capital of France?" in result.response,
                expected=True,
                actual=result.response,
            )
            # Assertion 5: Valid correlation UUID
            res.add_assertion(
                "valid_correlation_uuid",
                isinstance(result.trace.interaction_id, UUID),
                expected=True,
                actual=type(result.trace.interaction_id).__name__,
            )
            # Assertion 6: Latency metrics exist
            res.add_assertion(
                "latency_metrics_captured",
                result.metrics.total_interaction_ms is not None,
                expected=True,
                actual=result.metrics.total_interaction_ms is not None,
            )

        runtime.close()
        service.close()

    res.resources_after = ResourceProbe.sample()
    res.finalize()
    return res
