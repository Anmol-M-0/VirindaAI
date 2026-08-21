from __future__ import annotations

import tempfile
from pathlib import Path
from time import sleep

from virinda.application.service import AssistantService
from virinda.core.acceptance.models import AcceptanceResult, TurnAcceptanceRecord
from virinda.core.acceptance.probes import ResourceProbe
from virinda.core.events import InMemoryEventBus
from virinda.core.tokenizer import StreamingSentenceTokenizer
from virinda.core.trace import VoiceInteractionState, VoiceTurnResult
from virinda.core.voice import VoiceInteractionController
from virinda.core.voice_runtime import VoiceTurnRuntime
from virinda.domain.audio import AudioFrame, AudioPolicy, VoiceActivity
from virinda.infrastructure.persistence.sqlite import SQLiteConversationStore
from virinda.infrastructure.providers.echo import EchoProvider
from virinda.infrastructure.providers.router import StaticProviderRouter


def run_barge_in_torture_scenario(trials_count: int = 30) -> AcceptanceResult:
    res = AcceptanceResult(scenario="Scenario C: 30-Trial Barge-In Torture Suite")
    res.resources_before = ResourceProbe.sample()

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "barge_in.sqlite3"
        store = SQLiteConversationStore(db_path)
        bus = InMemoryEventBus()
        router = StaticProviderRouter({"echo": EchoProvider()}, default="echo")
        service = AssistantService(router=router, store=store, event_bus=bus)

        class TortureVad:
            def reset(self):
                pass

            def process(self, frame):
                return VoiceActivity(True)

        class TortureRecognizer:
            def transcribe(self, frames):
                sleep(0.015)
                return "This is a long sentence meant to be interrupted."

        class TortureTTS:
            def synthesize(self, text):
                return [AudioFrame(b"tts_audio_frame")]

        class TortureOutput:
            def __init__(self):
                self.stopped_count = 0

            def play_interruptible(self, frames, *, cancel_event):
                for _ in range(100):
                    if cancel_event.is_set():
                        self.stopped_count += 1
                        return
                    sleep(0.005)

            def stop(self):
                self.stopped_count += 1

        output = TortureOutput()
        results: list[VoiceTurnResult] = []
        controller = VoiceInteractionController(
            policy=AudioPolicy(min_speech_ms=0, end_silence_ms=0),
            vad=TortureVad(),
        )
        runtime = VoiceTurnRuntime(
            service=service,
            controller=controller,
            recognizer=TortureRecognizer(),
            synthesizer=TortureTTS(),
            output=output,
            tokenizer=StreamingSentenceTokenizer(),
            on_turn_result=results.append,
        )

        for i in range(trials_count):
            controller.arm()
            controller.trigger_listening("wake_word")
            controller.on_audio(AudioFrame(b"pcm_frame"), now=0.0)
            controller.push_to_talk_released()

            # Varied interruption points:
            # 1/3 during STT/early start (sleep 0.002)
            # 1/3 during generation (sleep 0.01)
            # 1/3 during audio playback (sleep 0.03)
            phase = i % 3
            if phase == 0:
                sleep(0.002)
            elif phase == 1:
                sleep(0.01)
            else:
                sleep(0.03)

            if controller.stage == controller.stage.SPEAKING:
                controller.on_wake_while_speaking()
            else:
                runtime.stop(reason="barge_in")

            for _ in range(50):
                if len(results) > i:
                    break
                sleep(0.005)

        # Assertion 1: Exactly N trials registered
        res.add_assertion(
            "all_trials_registered",
            len(results) == trials_count,
            expected=trials_count,
            actual=len(results),
        )

        # Assertion 2: 100% of trials transitioned to INTERRUPTED state
        interrupted_count = sum(
            1
            for r in results
            if r.interrupted and r.trace.state == VoiceInteractionState.INTERRUPTED
        )
        res.add_assertion(
            "all_trials_interrupted_cleanly",
            interrupted_count == trials_count,
            expected=trials_count,
            actual=interrupted_count,
        )

        # Assertion 3: Zero post-cancellation playback leaks
        res.add_assertion(
            "audio_player_stop_invoked",
            output.stopped_count >= trials_count,
            expected=f">= {trials_count}",
            actual=output.stopped_count,
        )

        for idx, r in enumerate(results):
            record = TurnAcceptanceRecord(
                index=idx + 1,
                utterance=r.transcript,
                response=r.response,
                correlation_id=r.trace.interaction_id,
                interrupted=r.interrupted,
                latency=r.metrics,
                passed=r.interrupted and r.trace.state == VoiceInteractionState.INTERRUPTED,
            )
            res.records.append(record)

        runtime.close()
        service.close()

    res.resources_after = ResourceProbe.sample()
    res.finalize()
    return res
