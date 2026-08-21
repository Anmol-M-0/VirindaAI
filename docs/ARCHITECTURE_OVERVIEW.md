# Architecture Overview

This is the concise architecture companion to `ARCHITECTURE.md`. Use it when onboarding; use `ARCHITECTURE.md` for detailed ownership and invariants.

```text
                         +----------------------+
                         |   User / Desktop     |
                         | voice / GUI / CLI    |
                         +----------+-----------+
                                    |
                 +------------------+------------------+
                 |                                     |
                 v                                     v
        +-------------------+                  +-------------------+
        |      OVOS         |                  | Virinda IPC/GUI    |
        | message bus       |                  | Unix socket       |
        +---------+---------+                  +---------+---------+
                  |                                      |
      +-----------+-----------+                          |
      |           |           |                          |
      v           v           v                          v
 Listener       Core        Audio              +-------------------+
 wake/VAD/STT  skills      TTS/output          | AssistantService  |
      |           |           |                +---------+---------+
      +-----------+-----------+                          |
                  |                                      |
                  +----------------------+---------------+
                                         |
              +--------------------------+--------------------------+
              |             |            |             |            |
              v             v            v             v            v
           Memory        Alerts        Tools        Context       Providers
              |             |            |             |            |
              +-------------+------------+-------------+------------+
                                         |
                                      SQLite
```

## Ownership invariant

OVOS owns *voice runtime mechanics*. Virinda owns *product policy and durable application state*.

If a new feature requires microphone/VAD/STT/TTS ownership, implement it as an OVOS plugin/configuration rather than adding another competing voice loop to Virinda.

If a new feature requires product memory, permissions, tool policy, user preferences, automation, or desktop state, implement it in Virinda and expose only the smallest required OVOS adapter.
