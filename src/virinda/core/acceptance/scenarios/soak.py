from __future__ import annotations

import tempfile
from pathlib import Path
from time import sleep

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


def run_soak_scenario(cycles: int = 20, cycle_delay_s: float = 0.01) -> AcceptanceResult:
    res = AcceptanceResult(scenario="Scenario D: Resource Soak & Leak Evaluation")
    res.resources_before = ResourceProbe.sample()

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "soak.sqlite3"
        store = SQLiteConversationStore(db_path)
        bus = InMemoryEventBus()
        router = StaticProviderRouter({"echo": EchoProvider()}, default="echo")
        service = AssistantService(router=router, store=store, event_bus=bus)

        class SoakVad:
            def reset(self):
                pass

            def process(self, frame):
                return VoiceActivity(True)

        class SoakRecognizer:
            def __init__(self):
                self.turn = 0

            def transcribe(self, frames):
                self.turn += 1
                return f"soak test query number {self.turn}"

        class SoakTTS:
            def synthesize(self, text):
                return [AudioFrame(b"soak_audio")]

        class SoakOutput:
            def play_interruptible(self, frames, *, cancel_event):
                for _ in range(2):
                    if cancel_event.is_set():
                        return
                    sleep(0.002)

            def stop(self):
                pass

        output = SoakOutput()
        results: list[VoiceTurnResult] = []
        controller = VoiceInteractionController(
            policy=AudioPolicy(min_speech_ms=0, end_silence_ms=0),
            vad=SoakVad(),
        )
        runtime = VoiceTurnRuntime(
            service=service,
            controller=controller,
            recognizer=SoakRecognizer(),
            synthesizer=SoakTTS(),
            output=output,
            tokenizer=StreamingSentenceTokenizer(),
            on_turn_result=results.append,
        )

        for i in range(cycles):
            controller.arm()
            controller.trigger_listening("wake_word")
            controller.on_audio(AudioFrame(b"pcm_frame"), now=0.0)
            controller.push_to_talk_released()

            for _ in range(50):
                if len(results) > i:
                    break
                sleep(0.005)

            sleep(cycle_delay_s)

        res.add_assertion(
            "all_soak_cycles_completed",
            len(results) == cycles,
            expected=cycles,
            actual=len(results),
        )

        runtime.close()
        service.close()

    # Sample after closing runtime and DB
    sleep(0.05)
    res.resources_after = ResourceProbe.sample()

    # Assertion: No thread leaks (active threads after close <= threads before + 1 for test runner)
    if res.resources_before and res.resources_after:
        delta_threads = res.resources_after.thread_count - res.resources_before.thread_count
        res.add_assertion(
            "zero_thread_leaks",
            delta_threads <= 1,
            expected="<= 1 thread delta",
            actual=f"{delta_threads} delta threads",
        )

        delta_fds = res.resources_after.fd_count - res.resources_before.fd_count
        res.add_assertion(
            "zero_fd_leaks",
            delta_fds <= 3,  # Tolerating standard Python runtime FD reuse
            expected="<= 3 fd delta",
            actual=f"{delta_fds} delta FDs",
        )

    res.finalize()
    return res
