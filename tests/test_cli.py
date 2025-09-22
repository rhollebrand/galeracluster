import json
from unittest.mock import patch

from hogebrug_status.cli import main
from hogebrug_status.checker import BridgeStatus, BridgeStatusError


def build_status(is_open=True):
    return BridgeStatus(
        is_open=is_open,
        summary="Teststatus",
        observed_at=None,
        source_url="http://example.com",
        raw_fields={},
    )


def test_cli_text_output(capsys):
    with patch("hogebrug_status.cli.BridgeStatusChecker") as mock_checker:
        mock_checker.return_value.get_status.return_value = build_status(True)
        exit_code = main(["--bridge", "Hogebrug"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "is open" in captured.out
    assert "Bron: http://example.com" in captured.out


def test_cli_json_output(capsys):
    with patch("hogebrug_status.cli.BridgeStatusChecker") as mock_checker:
        mock_checker.return_value.get_status.return_value = build_status(False)
        exit_code = main(["--json"])

    assert exit_code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["is_open"] is False
    assert data["source_url"] == "http://example.com"


def test_cli_error(capsys):
    with patch("hogebrug_status.cli.BridgeStatusChecker") as mock_checker:
        mock_checker.return_value.get_status.side_effect = BridgeStatusError("kapot")
        exit_code = main([])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "kon de brugstatus" in captured.err.lower()
