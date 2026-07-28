"""Adapter rate/auth patterns must match real error strings but never the
incidental numerics (epoch-ms timestamps, ids, token counts) that appear in
every JSON event stream.

Regression for a field failure: an OpenCode worker's context-overflow error
was classified AUTH_ERROR because the event timestamp 1785252897401 ends in
401, matching the bare `401` alternative that every adapter carried.
fleet-status.sh greps the whole events file with `grep -qiE`, so patterns are
evaluated here with Python re in IGNORECASE, which these EREs are compatible
with.
"""
import re
from pathlib import Path

import pytest

ADAPTERS_DIR = (
    Path(__file__).resolve().parent.parent
    / "skills" / "fleet-delegation" / "scripts" / "adapters"
)
ADAPTER_FILES = sorted(ADAPTERS_DIR.glob("*.sh"))

# The exact line that caused the field misclassification, plus lookalikes.
INNOCENT_LINES = [
    '{"type":"step_start","timestamp":1785252897401,"sessionID":"ses_05"}',
    '{"type":"tool_use","timestamp":1785252894290,"part":{"id":"prt_x"}}',
    '"usage":{"input_tokens":44290,"output_tokens":1401}',
    '"snapshot":"c23faad3df48ea5128a23dd75c78b6ddf4522039"',
    "wrote 4010 bytes to util/out.py",
    "Engine protocol predict stream returned an error: "
    '{"code":500,"message":"Context size has been exceeded."}',
]

AUTH_LINES = [
    "HTTP 401 Unauthorized",
    "Error: 401",
    "server returned 401.",
    "(401)",
]

RATE_LINES = [
    "HTTP 429 Too Many Requests",
    "Error: 429",
    "status code 429",
]


def extract(adapter: Path, var: str) -> str:
    m = re.search(rf"^{var}='([^']*)'", adapter.read_text(), re.MULTILINE)
    assert m, f"{adapter.name} does not define {var}"
    return m.group(1)


@pytest.mark.parametrize("adapter", ADAPTER_FILES, ids=lambda p: p.name)
@pytest.mark.parametrize("var", ["ADAPTER_AUTH_PATTERNS", "ADAPTER_RATE_PATTERNS"])
def test_patterns_ignore_incidental_numerics(adapter, var):
    pattern = re.compile(extract(adapter, var), re.IGNORECASE)
    for line in INNOCENT_LINES:
        assert not pattern.search(line), (
            f"{adapter.name} {var} false-positives on: {line}"
        )


@pytest.mark.parametrize("adapter", ADAPTER_FILES, ids=lambda p: p.name)
def test_auth_patterns_still_match_real_401(adapter):
    pattern = re.compile(extract(adapter, "ADAPTER_AUTH_PATTERNS"), re.IGNORECASE)
    for line in AUTH_LINES:
        assert pattern.search(line), f"{adapter.name} misses real auth error: {line}"


@pytest.mark.parametrize("adapter", ADAPTER_FILES, ids=lambda p: p.name)
def test_rate_patterns_still_match_real_429(adapter):
    pattern = re.compile(extract(adapter, "ADAPTER_RATE_PATTERNS"), re.IGNORECASE)
    for line in RATE_LINES:
        assert pattern.search(line), f"{adapter.name} misses real rate error: {line}"
