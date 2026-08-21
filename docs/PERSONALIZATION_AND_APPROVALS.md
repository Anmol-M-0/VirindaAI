# Personalization, Memory, Briefings, and Approvals

## Purpose

This document describes the user-facing assistant behaviors added on top of the OVOS runtime. These behaviors are local Virinda application features; OVOS remains responsible for microphone, wake-word, VAD, STT, TTS, and the message bus.

## Memory capture

Virinda accepts high-confidence deterministic memory statements such as:

```text
remember my favorite color is blue
my preferred editor is neovim
```

Statements beginning with `I think` or `I believe` are stored with medium confidence (`0.6`) so the UI and future ranking layers can distinguish a tentative fact from an explicit one.

### Secrets are never stored

Virinda rejects deterministic capture of common secrets, including:

- passwords
- PINs/passcodes
- OTPs
- API keys/tokens
- private keys
- credit-card and bank-account secrets

This rejection is deliberate. The durable memory store is not a secret manager.

### Sensitive memory

A user may explicitly classify a fact as sensitive with language such as:

```text
remember privately my medical preference is ...
```

Sensitive memory remains local and is not included in the generic daily briefing. Private mode still disables durable memory writes entirely.

## Personalized briefing

`briefing()` is deterministic and local. It never calls the LLM.

The output may include:

1. configured display name;
2. up to three upcoming alerts;
3. unread notification count;
4. active meeting state;
5. active desktop application;
6. quiet-hours state.

Sensitive memory is intentionally excluded.

Examples:

```text
What's my morning briefing?
Give me my daily briefing.
```

The same briefing is available through the CLI, Unix IPC, desktop overlay, and Virinda's OVOS intent.

## Conversational approvals

Consequential tool requests create a short-lived approval token and a pending action state.

Example:

```text
User: open https://example.com
Virinda: I need your approval before opening that URL. Say yes to continue.
User: yes
Virinda: Done: ...
```

The raw token is not spoken or displayed in the natural-language path. Trusted UI/IPC clients may still use the explicit token APIs when a programmatic approval workflow is required.

Approval tokens are single-use and expire. The tool broker continues to enforce the risk policy even if a client attempts to bypass the natural-language confirmation layer.

## Privacy rules

| Behavior | Normal | Private | Quiet |
|---|---|---|---|
| Durable conversation history | yes | no | yes |
| Memory writes | yes | no | yes |
| Profile writes | yes | no | yes |
| Generic briefing | yes | allowed | yes |
| Proactive notifications | yes | no | no |
| Follow-up listening | yes | yes | no |

## Design principle

These features are deliberately implemented before the LLM boundary whenever the user's intent is unambiguous. This makes them deterministic, testable, and safer than prompting a model to perform stateful local actions.
