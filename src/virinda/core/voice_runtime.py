from __future__ import annotations

from collections.abc import Callable
from queue import Empty, Queue
from threading import Event, RLock, Thread, current_thread

from virinda.application.service import AssistantService
from virinda.core.trace import VoiceInteractionTrace, VoiceTurnResult
from virinda.core.voice import VoiceInteractionController, VoiceSignal
from virinda.domain.audio import AudioFrame, AudioOutput, SpeechRecognizer, SpeechSynthesizer
from virinda.domain.events import ResponseCompleted, ResponseDelta


class VoiceTurnRuntime:
    """Bridge realtime voice adapters to the single authoritative assistant service.

    Input is transcribed into ``AssistantService.ask``. Output deltas are sentence-batched
    into one serialized, interruptible TTS queue. The runtime never stores conversation
    history and never owns provider state.
    """

    def __init__(
        self,
        *,
        service: AssistantService,
        controller: VoiceInteractionController,
        recognizer: SpeechRecognizer,
        synthesizer: SpeechSynthesizer,
        output: AudioOutput,
        tokenizer,
        emit: Callable[[VoiceSignal], None] | None = None,
        on_turn_result: Callable[[VoiceTurnResult], None] | None = None,
    ) -> None:
        self.service = service
        self.controller = controller
        self.recognizer = recognizer
        self.synthesizer = synthesizer
        self.output = output
        self.tokenizer = tokenizer
        self.emit = emit or (lambda _signal: None)
        self.on_turn_result = on_turn_result or (lambda _result: None)
        self._turn_lock = RLock()
        self._tts_lock = RLock()
        self._tts_worker_stop: Event | None = None
        self._tts_worker: Thread | None = None
        self._response_complete = False
        self._tts_worker_queue: Queue[object] | None = None
        self._tts_worker_done: Event | None = None
        self._closed = False
        self._generation = 0
        self._current_trace: VoiceInteractionTrace | None = None
        self._latest_trace: VoiceInteractionTrace | None = None
        self.service.events.subscribe(self)
        self._external_emit = self.controller.emit
        self.controller.emit = self._on_controller_signal

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.service.events.unsubscribe(self)
        self._stop_tts()
        with self._turn_lock:
            self._generation += 1
        self.controller.cancel()

    def get_latest_trace(self) -> VoiceInteractionTrace | None:
        with self._turn_lock:
            return self._latest_trace

    def publish(self, event) -> None:
        if self._closed:
            return
        if isinstance(event, ResponseDelta):
            with self._turn_lock:
                if self._current_trace is not None:
                    self._current_trace.mark_llm_first_token()
            for sentence in self.tokenizer.feed(event.text):
                with self._turn_lock:
                    if self._current_trace is not None:
                        self._current_trace.mark_tts_first_sentence()
                self._enqueue_tts(sentence, event.generation_id)
        elif isinstance(event, ResponseCompleted):
            with self._turn_lock:
                if self._current_trace is not None:
                    self._current_trace.mark_llm_end(event.text)
            for sentence in self.tokenizer.flush():
                self._enqueue_tts(sentence, event.generation_id)
            self._mark_response_complete()

    def on_audio(self, frame: AudioFrame, *, now: float | None = None) -> None:
        self.controller.on_audio(frame, now=now)

    def push_to_talk_pressed(self) -> None:
        self.controller.push_to_talk_pressed()

    def push_to_talk_released(self) -> None:
        self.controller.push_to_talk_released()

    def toggle_listen(self) -> None:
        self.controller.toggle_listen()

    def stop(self, reason: str = "user") -> None:
        with self._turn_lock:
            self._generation += 1
            if self._current_trace is not None:
                self._current_trace.mark_barge_in()
        self._stop_tts()
        self.service.cancel(reason)
        self.controller.cancel()
        with self._turn_lock:
            if self._current_trace is not None:
                self._current_trace.mark_cancellation_complete()
                self._finalize_turn(interrupted=True)

    def _on_controller_signal(self, signal: VoiceSignal) -> None:
        if self._closed:
            return
        if signal.name == "wake_word":
            with self._turn_lock:
                self._current_trace = VoiceInteractionTrace()
                self._current_trace.mark_wake()
        elif signal.name == "utterance_ready":
            frames = tuple(self.controller.utterance())
            with self._turn_lock:
                if self._current_trace is None:
                    self._current_trace = VoiceInteractionTrace()
                self._current_trace.mark_stt_start()
                self._generation += 1
                generation = self._generation
                trace = self._current_trace
            self.controller.mark_processing()
            Thread(
                target=self._transcribe_and_ask,
                args=(frames, generation, trace),
                daemon=True,
                name="virinda-stt-turn",
            ).start()
        elif signal.name in {"barge_in", "cancelled"}:
            with self._turn_lock:
                self._generation += 1
                if self._current_trace is not None:
                    self._current_trace.mark_barge_in()
            self._stop_tts()
            if signal.name == "barge_in":
                self.service.cancel(str(signal.payload.get("reason", "barge_in")))
            with self._turn_lock:
                if self._current_trace is not None:
                    self._current_trace.mark_cancellation_complete()
                    self._finalize_turn(interrupted=True)
        self._external_emit(signal)
        self.emit(signal)

    def _transcribe_and_ask(
        self,
        frames: tuple[AudioFrame, ...],
        generation: int,
        trace: VoiceInteractionTrace,
    ) -> None:
        if not self._generation_is_current(generation):
            return
        try:
            text = self.recognizer.transcribe(frames).strip()
        except Exception as exc:
            if self._generation_is_current(generation):
                trace.mark_failed(str(exc))
                self.emit(VoiceSignal("stt_error", {"error": str(exc)}))
                self.controller.arm()
                self._finalize_turn(interrupted=False)
            return
        if not text:
            if self._generation_is_current(generation):
                trace.mark_failed("empty_transcript")
                self.emit(VoiceSignal("empty_transcript", {}))
                self.controller.arm()
                self._finalize_turn(interrupted=False)
            return
        if not self._generation_is_current(generation):
            return
        trace.mark_stt_end(text)
        self.emit(VoiceSignal("transcript", {"text": text}))
        with self._tts_lock:
            self._response_complete = False
        if not self._generation_is_current(generation):
            return
        trace.mark_llm_start()
        self.service.ask(text)

    def _generation_is_current(self, generation: int) -> bool:
        with self._turn_lock:
            return generation == self._generation and not self._closed

    def _enqueue_tts(self, sentence: str, generation_id: int) -> None:
        text = sentence.strip()
        if not text or self._closed:
            return
        with self._tts_lock:
            if self._tts_worker is None or not self._tts_worker.is_alive():
                stop_event = Event()
                worker_queue: Queue[object] = Queue(maxsize=16)
                done_event = Event()
                self._tts_worker_stop = stop_event
                self._tts_worker_queue = worker_queue
                self._tts_worker_done = done_event
                self.controller.speaking_started()
                self._tts_worker = Thread(
                    target=self._tts_loop,
                    args=(stop_event, worker_queue, done_event),
                    daemon=True,
                    name="virinda-tts",
                )
                self._response_complete = False
                self._tts_worker.start()
        try:
            worker_queue = self._tts_worker_queue
            if worker_queue is None:
                self.emit(VoiceSignal("tts_backpressure", {}))
                return
            worker_queue.put_nowait((generation_id, text))
        except Exception:
            self.emit(VoiceSignal("tts_backpressure", {}))

    def _mark_response_complete(self) -> None:
        if self._closed:
            return
        with self._tts_lock:
            self._response_complete = True
            worker = self._tts_worker
            done_event = self._tts_worker_done
            if done_event is not None:
                done_event.set()
        if worker is None:
            self.controller.speaking_finished(allow_follow_up=True)
            self._finalize_turn(interrupted=False)

    def _tts_loop(self, stop_event: Event, worker_queue: Queue[object], done_event: Event) -> None:
        first_audio_marked = False
        while not stop_event.is_set():
            try:
                item = worker_queue.get(timeout=0.05)
            except Empty:
                if done_event.is_set() and worker_queue.empty():
                    self.controller.speaking_finished(allow_follow_up=True)
                    with self._turn_lock:
                        if self._current_trace is not None:
                            self._current_trace.mark_tts_end()
                    self._finalize_turn(interrupted=False)
                    with self._tts_lock:
                        if self._tts_worker_stop is stop_event:
                            self._tts_worker = None
                            self._tts_worker_stop = None
                            self._tts_worker_queue = None
                            self._tts_worker_done = None
                            self._response_complete = False
                    return
                continue
            generation_id, text = item
            try:
                if not self.service.is_generation_current(generation_id):
                    continue
                audio = self.synthesizer.synthesize(text)
                if self.service.is_generation_current(generation_id) and not stop_event.is_set():
                    if not first_audio_marked:
                        with self._turn_lock:
                            if self._current_trace is not None:
                                self._current_trace.mark_tts_first_audio()
                        first_audio_marked = True
                    play_interruptible = getattr(self.output, "play_interruptible", None)
                    if callable(play_interruptible):
                        play_interruptible(audio, cancel_event=stop_event)
                    else:
                        self.output.play(audio)
            except Exception as exc:
                cancelled = stop_event.is_set() or not self.service.is_generation_current(
                    generation_id
                )
                if not cancelled and not self._closed:
                    self.emit(VoiceSignal("tts_error", {"error": str(exc)}))
            finally:
                worker_queue.task_done()

    def _stop_tts(self) -> None:
        with self._turn_lock:
            if self._current_trace is not None:
                self._current_trace.mark_audio_stop()
        with self._tts_lock:
            stop_event = self._tts_worker_stop
            worker_queue = self._tts_worker_queue
            worker = self._tts_worker
            if stop_event is not None:
                stop_event.set()
            if worker_queue is not None:
                while True:
                    try:
                        worker_queue.get_nowait()
                        worker_queue.task_done()
                    except Empty:
                        break
            self._tts_worker = None
            self._tts_worker_stop = None
            self._tts_worker_queue = None
            self._tts_worker_done = None
            self._response_complete = False
        self.output.stop()
        if worker is not None and worker is not current_thread():
            worker.join(timeout=0.5)

    def _finalize_turn(self, *, interrupted: bool) -> None:
        with self._turn_lock:
            trace = self._current_trace
            if trace is None:
                return
            if not interrupted:
                trace.mark_completed()
            self._latest_trace = trace
            self._current_trace = None
            metrics = trace.compute_metrics()
            result = VoiceTurnResult(
                trace=trace,
                metrics=metrics,
                transcript=trace.transcript,
                response=trace.response_text,
                interrupted=interrupted,
            )
        try:
            self.on_turn_result(result)
        except Exception:
            pass
