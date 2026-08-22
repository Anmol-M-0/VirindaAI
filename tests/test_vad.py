from __future__ import annotations

import math
import struct

from virinda.infrastructure.audio.vad import EnergyVAD, VADState


def generate_pcm_frame(
    freq: float = 440.0, sample_rate: int = 16000, duration_ms: int = 20, amplitude: float = 0.5
) -> bytes:
    """Generates a 20ms synthetic mono PCM frame."""
    num_samples = int(sample_rate * (duration_ms / 1000.0))
    samples = []
    for i in range(num_samples):
        t = float(i) / float(sample_rate)
        val = int(amplitude * 32767.0 * math.sin(2.0 * math.pi * freq * t))
        samples.append(val)
    return struct.pack(f"<{num_samples}h", *samples)


def test_vad_silence_state():
    vad = EnergyVAD(sample_rate=16000, frame_duration_ms=20)
    silence_frame = b"\x00" * 640  # 320 samples @ 16-bit

    for _ in range(10):
        res = vad.process_frame(silence_frame)
        assert res.state == VADState.SILENCE
        assert res.is_speech is False
        assert res.rms_energy == 0.0


def test_vad_speech_start_and_endpointing():
    vad = EnergyVAD(
        sample_rate=16000,
        frame_duration_ms=20,
        pre_roll_ms=60,
        endpoint_silence_ms=100,  # 5 silence frames to endpoint
    )

    silence_frame = b"\x00" * 640
    speech_frame = generate_pcm_frame(freq=300.0, amplitude=0.4)

    # 1. Feed silence -> stays in SILENCE
    for _ in range(3):
        res = vad.process_frame(silence_frame)
        assert res.state == VADState.SILENCE

    # 2. Feed speech -> transitions to SPEECH
    res = vad.process_frame(speech_frame)
    assert res.state == VADState.SPEECH
    assert res.is_speech is True
    assert res.rms_energy > 0.05

    # 3. Feed 5 silence frames -> transitions to ENDPOINT
    for i in range(5):
        res = vad.process_frame(silence_frame)
        if i < 4:
            assert res.state == VADState.SPEECH
        else:
            assert res.state == VADState.ENDPOINT

    # 4. Audio bytes recorded
    audio = vad.get_recorded_audio()
    assert len(audio) > 0


def test_vad_timeout():
    vad = EnergyVAD(
        sample_rate=16000,
        frame_duration_ms=20,
        max_duration_s=0.1,  # 5 frames max
    )

    speech_frame = generate_pcm_frame(freq=300.0, amplitude=0.4)
    for _ in range(5):
        res = vad.process_frame(speech_frame)

    assert res.state == VADState.TIMEOUT


def test_vad_reset():
    vad = EnergyVAD()
    speech_frame = generate_pcm_frame(freq=300.0, amplitude=0.4)
    vad.process_frame(speech_frame)
    assert len(vad.get_recorded_audio()) > 0

    vad.reset()
    assert vad._state == VADState.SILENCE
    assert len(vad.get_recorded_audio()) == 0
