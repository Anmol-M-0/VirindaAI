# Marina wake-word models

Marina does **not** bundle a fake or unrelated wake model. The production configuration expects a real `hey_marina` OpenWakeWord model at a user-supplied path.

## Required asset

Place the model at a path such as:

```text
~/.local/share/marina/models/hey_marina.tflite
```

and point the OVOS `hotwords.hey_marina.models` entry at the absolute path.

## Acceptance criteria

Before enabling passive wake in production, evaluate the model on the target microphone and room:

- false accepts per hour in normal ambient audio;
- false rejects across near/far speaking positions;
- detection latency;
- robustness while Marina is speaking;
- behavior with TV/music/background speech.

Do not ship a model merely because it works in a quiet developer test. Wake-word quality is hardware- and environment-dependent.

## Recommended experiment matrix

Record short clips covering silence, normal conversation, music, keyboard noise, fans/HVAC, TV/radio, and Marina TTS playback. Track each hit/miss with timestamp and scenario label. Keep recordings local and delete them after evaluation unless explicit consent is given for retention.
