from virinda.ovos.audio_diagnostics import AudioCommandResult, inspect_linux_audio


def test_audio_command_result_is_json_safe() -> None:
    result = AudioCommandResult(("wpctl", "status"), True, 0, "ok", "")
    payload = result.to_dict()
    assert payload["command"] == ["wpctl", "status"]
    assert payload["returncode"] == 0


def test_linux_audio_diagnostics_shape() -> None:
    report = inspect_linux_audio()
    assert report["platform"] == "linux"
    assert isinstance(report["pipewire_available"], bool)
    assert len(report["checks"]) == 5
