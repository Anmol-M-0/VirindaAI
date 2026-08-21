from __future__ import annotations

import argparse

from virinda.application.runtime import build_service
from virinda.config.settings import Settings
from virinda.core.voice_controller import VoiceController
from virinda.infrastructure.audio.player import LinuxAudioPlayer
from virinda.infrastructure.audio.recorder import LinuxAudioRecorder
from virinda.infrastructure.audio.speech import GroqWhisperSTT, NativeTTS


def run_ptt_loop(controller: VoiceController, *, no_tts: bool = False) -> None:
    """Run interactive Push-To-Talk conversation loop."""
    print("=" * 65)
    print("        VirindaAI Spoken Voice Interaction (Push-To-Talk)        ")
    print("=" * 65)
    print(f"• Audio Input  : {controller.recorder._backend or 'None'}")
    print(f"• Audio Output : {controller.tts._backend or 'None'}")
    print("• Instructions :")
    print("    1. Press [ENTER] to start speaking.")
    print("    2. Press [ENTER] again when done.")
    print("    3. Press [Ctrl+C] to interrupt/barge-in or exit.")
    print("=" * 65)

    while True:
        try:
            input("\n[IDLE] Press [ENTER] to speak... ")
            print(
                "[LISTENING 🔴] Recording microphone audio... (Press ENTER to finish)",
                end="",
                flush=True,
            )
            controller.start_listening()

            # Wait for user to finish speaking
            input()
            print("\n[THINKING 🧠] Processing speech & generating response...", flush=True)
            controller.stop_listening_and_process(stream_stdout=True, speak_output=not no_tts)

        except (KeyboardInterrupt, EOFError):
            print("\n[INTERRUPT ⚡] Interrupted active turn.")
            controller.barge_in()
            try:
                choice = input("\nContinue conversation? ([y]/n): ").strip().lower()
                if choice in ("n", "no", "q", "quit", "exit"):
                    print("Goodbye!")
                    break
            except (KeyboardInterrupt, EOFError):
                print("\nExiting Virinda Voice.")
                break


def main() -> None:
    parser = argparse.ArgumentParser(description="VirindaAI Live Voice Interaction Interface")
    parser.add_argument(
        "--mode",
        "-m",
        choices=["ptt", "wake", "continuous"],
        default="ptt",
        help="Voice interaction mode (default: ptt)",
    )
    parser.add_argument(
        "--no-tts", action="store_true", help="Disable spoken audio synthesis output"
    )
    parser.add_argument(
        "--mock", action="store_true", help="Use offline mock STT/audio for testing"
    )
    args = parser.parse_args()

    settings = Settings.from_env()
    service = build_service(settings)

    recorder = LinuxAudioRecorder()
    player = LinuxAudioPlayer()
    tts = NativeTTS()
    stt = GroqWhisperSTT()

    controller = VoiceController(
        service=service,
        recorder=recorder,
        player=player,
        tts=tts,
        stt=stt,
    )

    if args.mode == "ptt":
        run_ptt_loop(controller, no_tts=args.no_tts)
    else:
        print(f"Mode '{args.mode}' will be supported in v0.27.2. Using Push-To-Talk.")
        run_ptt_loop(controller, no_tts=args.no_tts)


if __name__ == "__main__":
    main()
