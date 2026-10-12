"""CLI tests: argument parsing and the main() flow with mocked I/O."""

from unittest import mock

import sysaudit


def test_parse_args_defaults():
    args = sysaudit.parse_args([])
    assert args.format == "both"
    assert args.output == "."


def test_parse_args_format_choices():
    for fmt in ("html", "json", "both"):
        assert sysaudit.parse_args(["--format", fmt]).format == fmt


def test_main_runs_collectors_and_writes(tmp_path):
    fake_inventory = {"os": {"hostname": "X"}}
    with mock.patch(
        "sysaudit.run_all", return_value=fake_inventory
    ) as m_run, mock.patch(
        "sysaudit.write_reports", return_value=["/tmp/x.html"]
    ) as m_write:
        rc = sysaudit.main(["--format", "json", "--output", str(tmp_path)])
    assert rc == 0
    m_run.assert_called_once()
    m_write.assert_called_once()
    assert m_write.call_args.args[0] is fake_inventory
    assert m_write.call_args.kwargs["fmt"] == "json"
