from pathlib import Path

from virinda.ovos.doctor import run_doctor


def test_doctor_reports_persona_and_model_checks(tmp_path: Path):
    root = Path(__file__).parents[1]
    report = run_doctor(root)
    names = {check.name for check in report.checks}
    assert {"persona", "wake-model", "OVOS config template"} <= names
    persona = next(check for check in report.checks if check.name == "persona")
    assert persona.status == "ok"
    stt = next(check for check in report.checks if check.name == "whispercpp-stt")
    assert stt.required is True


def test_doctor_accepts_explicit_wake_model(monkeypatch, tmp_path: Path):
    root = Path(__file__).parents[1]
    model = tmp_path / "hey_virinda.tflite"
    model.write_bytes(b"model")
    monkeypatch.setenv("VIRINDA_WAKE_MODEL", str(model))
    report = run_doctor(root)
    wake = next(check for check in report.checks if check.name == "wake-model")
    assert wake.status == "ok"


def test_doctor_can_emit_service_checks_without_systemd(tmp_path: Path):
    root = Path(__file__).parents[1]
    report = run_doctor(root, check_services=True)
    names = {check.name for check in report.checks}
    assert {"messagebus-service", "core-service", "listener-service", "audio-service"} <= names


def test_nats_doctor_is_optional(monkeypatch, tmp_path):
    monkeypatch.setenv("VIRINDA_JOB_BROKER", "inprocess")
    report = run_doctor(tmp_path, check_nats=True)
    names = {check.name for check in report.checks}
    assert "nats-py" in names
    assert "nats-url" in names


def test_nats_doctor_marks_backend_required(monkeypatch, tmp_path):
    monkeypatch.setenv("VIRINDA_JOB_BROKER", "nats")
    report = run_doctor(tmp_path, check_nats=True)
    nats_check = next(check for check in report.checks if check.name == "nats-py")
    assert nats_check.required is True
