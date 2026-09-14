import sys

import pytest

from qwork.errors import QworkError
from qwork.runner import CommandError, run


def test_run_returns_stdout():
    assert run([sys.executable, "-c", "print('hi')"]) == "hi\n"


def test_run_raises_command_error_with_stderr():
    with pytest.raises(CommandError) as info:
        run([sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"])
    assert info.value.returncode == 3
    assert info.value.stderr == "boom"
    assert "boom" in str(info.value)


def test_run_missing_executable_is_a_user_error():
    with pytest.raises(QworkError, match="not on PATH"):
        run(["definitely-not-a-real-command-xyz"])
