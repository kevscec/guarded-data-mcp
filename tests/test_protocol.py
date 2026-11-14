import pytest

from evals.runner import run


@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_cli_full_state_and_real_stdio_protocol(mode):
    report = run(mode)
    assert report["status"] == "passed"
    assert report["passed"] == 18
    assert report["real_agent"] is False
