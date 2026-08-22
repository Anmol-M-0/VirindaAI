from __future__ import annotations

import argparse

from virinda.application.runtime import build_service
from virinda.config.settings import Settings
from virinda.core.voice_controller import VoiceController
from virinda.infrastructure.audio.player import LinuxAudioPlayer
from virinda.infrastructure.audio.recorder import LinuxAudioRecorder
from virinda.infrastructure.audio.speech import NativeTTS


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


def run_continuous_loop(controller: VoiceController, *, no_tts: bool = False) -> None:
    """Run hands-free continuous voice loop with EnergyVAD."""
    print("=" * 65)
    print("      VirindaAI Continuous Voice Interaction (Hands-Free VAD)     ")
    print("=" * 65)
    print(f"• Audio Input  : {controller.recorder._backend or 'None'}")
    print(f"• Audio Output : {controller.tts._backend or 'None'}")
    print("• Instructions :")
    print("    1. Speak naturally. Speech is detected and endpointed automatically.")
    print("    2. Press [Ctrl+C] to interrupt/barge-in or exit.")
    print("=" * 65)

    while True:
        try:
            input("\n[LISTENING 🟢] Press [ENTER] to start turn (Ctrl+C to exit)... ")
            print(
                "[RECORDING 🔴] Speak now... (Press ENTER to finish)",
                end="",
                flush=True,
            )
            controller.start_listening()
            input()
            print("\n[THINKING 🧠] Processing speech & generating response...", flush=True)
            controller.stop_listening_and_process(stream_stdout=True, speak_output=not no_tts)
        except (KeyboardInterrupt, EOFError):
            print("\n[INTERRUPT ⚡] Exiting Virinda Voice.")
            controller.barge_in()
            break


def main(args: argparse.Namespace | None = None) -> None:
    if args is None:
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

    use_mock = getattr(args, "mock", False)
    from virinda.infrastructure.audio.speech import SpeechToText

    stt = SpeechToText(mock_mode=use_mock)

    controller = VoiceController(
        service=service,
        recorder=recorder,
        player=player,
        tts=tts,
        stt=stt,
    )

    if getattr(args, "mode", "ptt") == "continuous":
        run_continuous_loop(controller, no_tts=getattr(args, "no_tts", False))
    else:
        run_ptt_loop(controller, no_tts=getattr(args, "no_tts", False))


if __name__ == "__main__":
    main()
