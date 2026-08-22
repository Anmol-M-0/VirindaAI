# VirindaAI User Manual & Operational Guide (v0.28.0)

VirindaAI is a local-first ambient desktop assistant for Linux built on top of OpenVoiceOS (OVOS) and native Linux audio/IPC primitives. It provides an authoritative cognitive turn coordinator (`AssistantService`), persistent SQLite WAL memory, Linux desktop context grounding, ephemeral risk-based approval gating, and dual-mode voice interaction (Standalone `EnergyVAD` or full OVOS message bus).

---

## 1. Quickstart & First Run

### Prerequisites
- **Operating System**: Linux (x86_64 or aarch64).
- **Audio Stack**: PipeWire (`pw-record`, `pw-play`) or ALSA (`arecord`, `aplay`).
- **Speech Synthesis (Local)**: `spd-say` or `espeak-ng`.
- **Python Environment**: Python 3.11 or 3.12 managed via `uv`.

### 30-Second Quickstart
```bash
# Navigate to the repository
cd VirindAI

# 1. Verify system status and storage integrity
./virinda status

# 2. Test a basic text prompt
./virinda ask "Hello Virinda, what can you do?"

# 3. Start interactive voice mode (Push-to-Talk)
./virinda voice --mode ptt

# 4. Start hands-free voice mode (Continuous EnergyVAD)
./virinda voice --mode continuous
```

---

## 2. Voice Interaction Modes

VirindaAI supports multiple interaction modes depending on your desktop workflow:

### A. Push-to-Talk Mode (`--mode ptt`)
Optimal for noisy environments or focused command execution.
```bash
./virinda voice --mode ptt
```
- **How it works**:
  1. Press `[ENTER]` when you are ready to speak.
  2. Speak your command (e.g. *"What is the weather today?"*).
  3. Press `[ENTER]` to finish speaking.
  4. Virinda generates the response and begins streaming spoken speech concurrently.

### B. Hands-Free Continuous Mode (`--mode continuous`)
Hands-free continuous conversation powered by `EnergyVAD`.
```bash
./virinda voice --mode continuous
```
- **How it works**:
  1. Virinda continuously listens to the microphone in the background.
  2. When you start speaking, the RMS energy and Zero-Crossing Rate (ZCR) automatically detect speech onset.
  3. A 300ms pre-roll ring buffer ensures your first syllables are preserved.
  4. When you stop speaking for 800ms, Virinda automatically endpoints the turn, transcribes via STT, and replies.

### C. Voice Options & Flags
- `--no-tts`: Disables audio playback; prints the transcript and LLM response to the terminal.
- `--mock`: Uses offline synthetic audio and mock STT (ideal for automated CI and testing).

```bash
./virinda voice --mode ptt --no-tts
```

---

## 3. Command-Line Reference

VirindaAI provides a complete set of subcommands under `./virinda`:

```text
virinda [-h] [--data-dir DATA_DIR] [--socket SOCKET] <command> [arguments]
```

### Core Commands

| Command | Syntax | Description |
| :--- | :--- | :--- |
| `status` | `./virinda status` | Dumps runtime JSON status including providers, audio devices, persistence, and capabilities. |
| `doctor` | `./virinda doctor` | Evaluates OVOS and desktop dependencies. |
| `ask` | `./virinda ask "<prompt>"` | Executes a single text query and prints the response. |
| `voice` | `./virinda voice [--mode {ptt,continuous}]` | Launches the interactive spoken voice assistant loop. |
| `history` | `./virinda history [--limit N]` | Displays past conversation turns with timestamps and correlation IDs. |
| `sessions` | `./virinda sessions` | Lists active and historical conversational sessions. |
| `clear` | `./virinda clear` | Resets the conversation context for the current session. |
| `backup` | `./virinda backup` | Creates an atomic copy of the SQLite database and WAL journal. |

---

## 4. LLM Providers & Model Selection

VirindaAI features pluggable LLM backends:

```bash
# List available providers
./virinda providers

# Select the Universal 'ask' CLI Bridge (ChatGPT, NIM, Groq, OpenRouter)
./virinda provider ask

# Select direct Groq cloud inference
./virinda provider groq

# Select offline deterministic echo (testing)
./virinda provider echo
```

---

## 5. Cognitive Memory & Notes

VirindaAI maintains durable long-term memory in SQLite WAL. It ranks memories using a hybrid scoring algorithm combining BM25 lexical token overlap ($40\%$), local FastEmbed dense cosine similarity ($30\%$), confidence calibration ($15\%$), and exponential recency decay ($15\%$).

```bash
# Add a durable fact
./virinda memory add "My primary development environment is Neovim on Hyprland."

# List all stored memories and notes
./virinda memory list

# Perform a hybrid semantic search across memories
./virinda memory rank "Which editor do I use on Wayland?"
```

---

## 6. Proactive Briefings & Desktop Signals

Virinda integrates directly with Linux desktop compositors (Hyprland, Sway, X11):

```bash
# Generate a desktop briefing
./virinda briefing

# Inspect current window title, active application, and compositor
./virinda desktop-signals

# List scheduled automation routines
./virinda routines list

# Inspect unread system notifications
./virinda notifications list
```

---

## 7. Tool Execution & Ephemeral Approvals

VirindaAI enforces a strict 3-tier risk boundary:
- **`read_only`**: Allowed without confirmation (e.g. `get_system_info`, `search_memory`).
- **`local_write`**: Local modifications with logging.
- **`destructive`**: Requires explicit cryptographic confirmation via `ApprovalManager`.

```bash
# List registered tools
./virinda tools

# Execute a safe tool
./virinda tool system_info '{}'

# Destructive tool execution flow
# If a tool requires approval, Virinda will generate a single-use token:
# "Action 'power_action' requires user confirmation. Token: a7f8c9e1..."
# Confirm execution with the token:
./virinda tool power_action '{"action": "suspend"}' --token a7f8c9e1
```

---

## 8. OpenVoiceOS (OVOS) Bridge

When running OpenVoiceOS on Linux, Virinda seamlessly connects as the brain and skill provider over the OVOS MessageBus:

```bash
# Connect Virinda to the OVOS message bus (ws://127.0.0.1:8181/core)
./virinda ovos bridge
```

In OVOS mode:
- `ovos-dinkum-listener` and `ovos-vad-plugin-silero` handle wake words and neural VAD.
- Virinda listens for `recognizer_loop:utterance` events, generates streaming tokens, and dispatches `speak` messages back to the bus.

---

## 9. Systemd User Daemon Setup

To run VirindaAI automatically in the background on user login:

1. **Install the User Service**:
   ```bash
   mkdir -p ~/.config/systemd/user
   cp packaging/systemd/virinda.service ~/.config/systemd/user/
   ```

2. **Enable and Start the Service**:
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable --now virinda.service
   ```

3. **Check Service Status & Logs**:
   ```bash
   systemctl --user status virinda.service
   journalctl --user -u virinda.service -f
   ```

---

## 10. Benchmarks & Acceptance Gates

You can run our built-in test runners and benchmarking suites to verify local audio latency and system stability:

```bash
# Run a 10-turn voice latency benchmark
./virinda benchmark --turns 10

# Run the 5 End-to-End Voice Acceptance Scenarios (Cold start, Conversation, Barge-in, Soak, Desktop)
./virinda acceptance voice

# Execute the full 6-Stage Release Gate
./scripts/release_check.sh
```
