from __future__ import annotations

from pathlib import Path

from virinda.interfaces.doctor import CheckResult, DiagnosticRunner, DiagnosticStatus, DoctorReport


def test_diagnostic_runner_all_checks(tmp_path: Path):
    runner = DiagnosticRunner(db_path=tmp_path / "test.sqlite3", check_timeout_seconds=0.5)
    report = runner.run_all()

    assert isinstance(report, DoctorReport)
    assert report.is_healthy is True
    assert report.total_latency_ms > 0.0
    assert len(report.checks) == 5

    names = {c.name for c in report.checks}
    assert "audio_subsystem" in names
    assert "desktop_compositor" in names
    assert "sqlite_database" in names
    assert "ovos_message_bus" in names
    assert "semantic_embeddings" in names


def test_diagnostic_runner_to_dict():
    report = DoctorReport(
        overall_status=DiagnosticStatus.PASS,
        checks=[
            CheckResult(
                name="test_check",
                category="test",
                status=DiagnosticStatus.PASS,
                message="All good",
                latency_ms=1.2,
            )
        ],
        total_latency_ms=1.2,
    )
    d = report.to_dict()
    assert d["overall_status"] == "PASS"
    assert d["check_count"] == 1
