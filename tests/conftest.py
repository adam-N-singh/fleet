"""Shared helpers: run the fleet's Python tools as subprocesses (the same
contract the bash scripts use — argv in, stdout/exit code out), hermetically
isolated from any real registry or ledger on the machine."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "fleet-delegation" / "scripts"


def run_tool(script, *args, env=None, cwd=None):
    """Run a scripts/*.py tool with an isolated environment."""
    e = os.environ.copy()
    # Point HOME (POSIX) and USERPROFILE (Windows) away from the real home so
    # ~/.fleet/providers.json on a developer machine can never leak into tests.
    if env:
        e.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True, text=True, env=e, cwd=cwd,
    )


@pytest.fixture
def isolated_env(tmp_path):
    """Env overrides that make registry/ledger resolution hermetic."""
    home = tmp_path / "home"
    home.mkdir()
    return {
        "HOME": str(home),
        "USERPROFILE": str(home),
        "FLEET_PROVIDERS": "",  # empty string = unset for the search list
    }
