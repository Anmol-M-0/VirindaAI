import json
from unittest.mock import patch

from virinda.interfaces.cli import main


def test_cli_benchmark_mock_run(capsys):
    test_args = ["virinda", "benchmark", "--mock", "--turns", "3", "--json"]
    with patch("sys.argv", test_args):
        main()

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["summary"]["total_turns"] == 3
    assert data["summary"]["completed_turns"] == 3
    assert data["summary"]["overall_passed"] is True
    assert data["metrics"]["stt"]["p50_ms"] is not None
    assert len(data["gates"]) >= 2
