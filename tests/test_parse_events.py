"""parse_events.py: every adapter output format, tested against stubs that
mimic each CLI's documented output shape. Empty/missing values exit 1;
unknown formats exit 2; garbage degrades gracefully."""
import json

from conftest import run_tool


def parse(tmp_path, content, field, fmt, name="out.log"):
    p = tmp_path / name
    # newline="" so crafted \r\n sequences reach the parser byte-for-byte
    # (default newline translation would double them on Windows)
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    return run_tool("parse_events.py", str(p), field, "--format", fmt)


def jsonl(*events):
    return "\n".join(json.dumps(e) for e in events) + "\n"


# ---------- codex (codex exec --json JSONL) ---------------------------------

CODEX_OK = jsonl(
    {"type": "thread.started", "thread_id": "th_123"},
    {"type": "item.completed", "item": {"type": "agent_message", "text": "first draft"}},
    {"type": "item.completed", "item": {"type": "agent_message", "text": "all done"}},
    {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}},
)


def test_codex_session(tmp_path):
    r = parse(tmp_path, CODEX_OK, "session", "codex")
    assert r.returncode == 0 and r.stdout.strip() == "th_123"


def test_codex_final_is_last_agent_message(tmp_path):
    r = parse(tmp_path, CODEX_OK, "final", "codex")
    assert r.stdout.strip() == "all done"


def test_codex_usage_and_completed(tmp_path):
    r = parse(tmp_path, CODEX_OK, "usage", "codex")
    assert json.loads(r.stdout)["input_tokens"] == 10
    r = parse(tmp_path, CODEX_OK, "completed", "codex")
    assert r.stdout.strip() == "yes"


def test_codex_not_completed_without_turn_completed(tmp_path):
    content = jsonl({"type": "thread.started", "thread_id": "th_1"})
    r = parse(tmp_path, content, "completed", "codex")
    assert r.stdout.strip() == "no"


def test_codex_errors(tmp_path):
    content = jsonl({"type": "error", "message": "boom"},
                    {"type": "turn.failed", "reason": "x"})
    r = parse(tmp_path, content, "errors", "codex")
    assert "boom" in r.stdout and "turn.failed" in r.stdout


def test_codex_garbage_lines_skipped(tmp_path):
    content = "not json at all\n" + CODEX_OK + "}{]broken\n"
    r = parse(tmp_path, content, "final", "codex")
    assert r.stdout.strip() == "all done"


# ---------- opencode (opencode run --format json NDJSON) --------------------

OPENCODE_OK = jsonl(
    {"type": "step_start", "part": {"sessionID": "ses_abc"}},
    {"type": "text", "part": {"text": "created the file"}},
    {"type": "step-finish", "part": {"tokens": {"input": 21660, "output": 91}, "cost": 0}},
)


def test_opencode_session_found_recursively(tmp_path):
    r = parse(tmp_path, OPENCODE_OK, "session", "opencode")
    assert r.stdout.strip() == "ses_abc"


def test_opencode_final_joins_text_parts(tmp_path):
    r = parse(tmp_path, OPENCODE_OK, "final", "opencode")
    assert "created the file" in r.stdout


def test_opencode_usage_both_spellings(tmp_path):
    r = parse(tmp_path, OPENCODE_OK, "usage", "opencode")
    assert json.loads(r.stdout)["tokens"]["input"] == 21660
    alt = jsonl({"type": "step_finish", "part": {"cost": 0.01}})
    r = parse(tmp_path, alt, "usage", "opencode")
    assert json.loads(r.stdout)["cost"] == 0.01


def test_opencode_error_event(tmp_path):
    content = jsonl({"type": "error", "error": {"name": "UnknownError",
                                                "data": {"message": "exceeds the available context size"}}})
    r = parse(tmp_path, content, "errors", "opencode")
    assert "context size" in r.stdout
    r = parse(tmp_path, content, "completed", "opencode")
    assert r.stdout.strip() == "no"


# ---------- gemini (one JSON object) ----------------------------------------

GEMINI_OK = json.dumps({"response": "done and dusted", "stats": {"tokens": 42}})


def test_gemini_fields(tmp_path):
    assert parse(tmp_path, GEMINI_OK, "final", "gemini").stdout.strip() == "done and dusted"
    assert json.loads(parse(tmp_path, GEMINI_OK, "usage", "gemini").stdout)["tokens"] == 42
    assert parse(tmp_path, GEMINI_OK, "completed", "gemini").stdout.strip() == "yes"
    assert parse(tmp_path, GEMINI_OK, "session", "gemini").returncode == 1  # no session


def test_gemini_object_with_stray_log_lines(tmp_path):
    content = "Loading config...\n" + GEMINI_OK
    r = parse(tmp_path, content, "final", "gemini")
    assert r.stdout.strip() == "done and dusted"


def test_gemini_error(tmp_path):
    content = json.dumps({"error": {"code": 429, "message": "quota"}})
    assert "quota" in parse(tmp_path, content, "errors", "gemini").stdout
    assert parse(tmp_path, content, "completed", "gemini").stdout.strip() == "no"


# ---------- claude (claude -p --output-format json result object) -----------

CLAUDE_OK = json.dumps({"type": "result", "subtype": "success",
                        "result": "implemented it", "session_id": "s-77",
                        "total_cost_usd": 0.0123, "usage": {"output_tokens": 9}})


def test_claude_fields(tmp_path):
    assert parse(tmp_path, CLAUDE_OK, "session", "claude").stdout.strip() == "s-77"
    assert parse(tmp_path, CLAUDE_OK, "final", "claude").stdout.strip() == "implemented it"
    usage = json.loads(parse(tmp_path, CLAUDE_OK, "usage", "claude").stdout)
    assert usage["total_cost_usd"] == 0.0123
    assert parse(tmp_path, CLAUDE_OK, "completed", "claude").stdout.strip() == "yes"


def test_claude_error_subtype(tmp_path):
    content = json.dumps({"type": "result", "subtype": "error_max_turns", "result": "gave up"})
    assert parse(tmp_path, content, "completed", "claude").stdout.strip() == "no"
    assert "error_max_turns" in parse(tmp_path, content, "errors", "claude").stdout


# ---------- ndjson (cursor-agent / qwen stream-json) ------------------------

NDJSON_OK = jsonl(
    {"type": "system", "session_id": "cur-1"},
    {"type": "assistant", "message": {"content": [{"type": "text", "text": "working"}]}},
    {"type": "result", "subtype": "success", "result": "finished the task",
     "usage": {"input_tokens": 100}},
)


def test_ndjson_fields(tmp_path):
    assert parse(tmp_path, NDJSON_OK, "session", "ndjson").stdout.strip() == "cur-1"
    assert parse(tmp_path, NDJSON_OK, "final", "ndjson").stdout.strip() == "finished the task"
    assert json.loads(parse(tmp_path, NDJSON_OK, "usage", "ndjson").stdout)["input_tokens"] == 100
    assert parse(tmp_path, NDJSON_OK, "completed", "ndjson").stdout.strip() == "yes"


def test_ndjson_error_result(tmp_path):
    content = jsonl({"type": "result", "subtype": "error", "is_error": True})
    assert parse(tmp_path, content, "completed", "ndjson").stdout.strip() == "no"
    assert parse(tmp_path, content, "errors", "ndjson").returncode == 0


# ---------- grok (generic object, unpublished schema) -----------------------

def test_grok_generic_key_search(tmp_path):
    content = json.dumps({"meta": {"session": {"id": "g-9"}},
                          "output": {"final": "grok says done"},
                          "usage": {"total_tokens": 55}})
    assert parse(tmp_path, content, "session", "grok").stdout.strip() == "g-9"
    assert parse(tmp_path, content, "final", "grok").stdout.strip() == "grok says done"
    assert json.loads(parse(tmp_path, content, "usage", "grok").stdout)["total_tokens"] == 55
    assert parse(tmp_path, content, "completed", "grok").stdout.strip() == "yes"


def test_grok_error_means_not_completed(tmp_path):
    content = json.dumps({"error": "denied", "response": "partial"})
    assert parse(tmp_path, content, "completed", "grok").stdout.strip() == "no"


# ---------- text (copilot, amp, antigravity) --------------------------------

def test_text_strips_ansi_and_cr(tmp_path):
    content = "\x1b[1mThe answer\x1b[0m is\r\n42\r\n"
    r = parse(tmp_path, content, "final", "text")
    assert r.stdout.strip() == "The answer is\n42"
    assert parse(tmp_path, content, "completed", "text").stdout.strip() == "yes"


def test_text_empty_file_exits_1(tmp_path):
    r = parse(tmp_path, "", "final", "text")
    assert r.returncode == 1
    r = parse(tmp_path, "", "completed", "text")
    assert r.stdout.strip() == "no"


def test_antigravity_is_text_alias(tmp_path):
    r = parse(tmp_path, "plain response", "final", "antigravity")
    assert r.stdout.strip() == "plain response"


# ---------- contract edges ---------------------------------------------------

def test_unknown_format_exits_2(tmp_path):
    r = parse(tmp_path, "x", "final", "carrier-pigeon")
    assert r.returncode == 2


def test_missing_file_exits_nonzero():
    r = run_tool("parse_events.py", "no/such/file.log", "final", "--format", "codex")
    assert r.returncode == 1
