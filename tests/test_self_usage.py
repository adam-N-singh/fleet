"""self_usage.py: transcript resolution, usage summing/dedup, pricing at
supervisor rates, and the snapshot/delta measurement flow."""
import json
import os
import re

from conftest import run_tool


def slug(path):
    # mirrors the script's cwd_slug rule (verified against a real Claude Code
    # project dir: C:\Users\... -> C--Users-...)
    return re.sub(r"[^A-Za-z0-9-]", "-", os.path.abspath(str(path)))


def claude_line(msg_id, inp, out, cr=0, cw=0):
    return json.dumps({"type": "assistant", "message": {"id": msg_id, "usage": {
        "input_tokens": inp, "output_tokens": out,
        "cache_read_input_tokens": cr, "cache_creation_input_tokens": cw}}})


def write_claude_transcript(tmp_path, lines, name="sess.jsonl"):
    d = tmp_path / "home" / ".claude" / "projects" / slug(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text("".join(l + "\n" for l in lines), encoding="utf-8")
    return p


def write_supervisor_registry(tmp_path, sup):
    reg = {"providers": {"codex": {"enabled": True, "adapter": "codex",
                                   "access": "subscription"}},
           "supervisor": sup}
    p = tmp_path / "providers.json"
    p.write_text(json.dumps(reg), encoding="utf-8")
    return str(p)


# ---------- sum --------------------------------------------------------------

def test_sum_dedups_streamed_lines_by_message_id(tmp_path, isolated_env):
    # one streamed message writes several lines with cumulative usage —
    # only the last line per id may count, or self-cost is overstated
    write_claude_transcript(tmp_path, [
        claude_line("m1", 10, 50),          # partial flush of m1
        claude_line("m1", 10, 200, cr=1000, cw=30),  # final counts for m1
        claude_line("m2", 5, 100),
        "{not json",                         # tolerated
    ])
    r = run_tool("self_usage.py", "sum", env=isolated_env, cwd=tmp_path)
    assert r.returncode == 0
    assert "harness=claude" in r.stdout
    assert "TURNS 2" in r.stdout
    assert "TOKENS input=15 output=300 cache_read=1000 cache_write=30" in r.stdout


def test_sum_no_transcript_exits_1(tmp_path, isolated_env):
    r = run_tool("self_usage.py", "sum", env=isolated_env, cwd=tmp_path)
    assert r.returncode == 1
    assert "NO TRANSCRIPT" in r.stderr
    assert "parity estimate" in r.stderr


def test_sum_explicit_transcript_override(tmp_path, isolated_env):
    p = tmp_path / "elsewhere.jsonl"
    p.write_text(claude_line("m1", 1, 2) + "\n", encoding="utf-8")
    r = run_tool("self_usage.py", "sum", "--transcript", str(p),
                 env=isolated_env, cwd=tmp_path)
    assert r.returncode == 0
    assert "TOKENS input=1 output=2" in r.stdout


def test_sum_prices_with_assumed_cache_rates(tmp_path, isolated_env):
    write_claude_transcript(tmp_path, [
        claude_line("m1", 1_000_000, 100_000, cr=1_000_000, cw=80_000),
    ])
    env = dict(isolated_env, FLEET_PROVIDERS=write_supervisor_registry(
        tmp_path, {"model": "m", "input_per_mtok": 10, "output_per_mtok": 30}))
    r = run_tool("self_usage.py", "sum", env=env, cwd=tmp_path)
    # 10 (input) + 3 (output) + 1 (cache_read @ input/10) + 1 (cache_write @ input*1.25)
    assert "COST_USD 15.0000" in r.stdout
    assert "cache rates assumed from input rate" in r.stdout


def test_sum_prices_with_explicit_cache_rates(tmp_path, isolated_env):
    write_claude_transcript(tmp_path, [
        claude_line("m1", 0, 0, cr=2_000_000, cw=1_000_000),
    ])
    env = dict(isolated_env, FLEET_PROVIDERS=write_supervisor_registry(
        tmp_path, {"model": "m", "input_per_mtok": 10, "output_per_mtok": 30,
                   "cache_read_per_mtok": 0.5, "cache_write_per_mtok": 2}))
    r = run_tool("self_usage.py", "sum", env=env, cwd=tmp_path)
    assert "COST_USD 3.0000" in r.stdout
    assert "assumed" not in r.stdout


def test_sum_without_rates_says_unavailable(tmp_path, isolated_env):
    write_claude_transcript(tmp_path, [claude_line("m1", 1, 2)])
    r = run_tool("self_usage.py", "sum", env=isolated_env, cwd=tmp_path)
    assert "COST_USD unavailable" in r.stdout


# ---------- snapshot / delta -------------------------------------------------

def test_snapshot_then_delta_measures_the_span(tmp_path, isolated_env):
    p = write_claude_transcript(tmp_path, [claude_line("m1", 10, 100, cr=500)])
    snap = tmp_path / "snap.json"
    r = run_tool("self_usage.py", "snapshot", "--file", str(snap),
                 env=isolated_env, cwd=tmp_path)
    assert r.returncode == 0 and "SNAPSHOT" in r.stdout
    # more work happens in the session
    with open(p, "a", encoding="utf-8") as f:
        f.write(claude_line("m2", 5, 40, cr=200, cw=7) + "\n")
    r = run_tool("self_usage.py", "delta", "--file", str(snap),
                 env=isolated_env, cwd=tmp_path)
    assert r.returncode == 0
    assert "SELF_USAGE_DELTA" in r.stdout
    assert "TURNS 1" in r.stdout
    assert "TOKENS input=5 output=40 cache_read=200 cache_write=7" in r.stdout


def test_delta_without_snapshot_exits_1(tmp_path, isolated_env):
    write_claude_transcript(tmp_path, [claude_line("m1", 1, 2)])
    r = run_tool("self_usage.py", "delta", "--file",
                 str(tmp_path / "missing.json"), env=isolated_env, cwd=tmp_path)
    assert r.returncode == 1
    assert "NO SNAPSHOT" in r.stderr


def test_delta_rejects_changed_transcript(tmp_path, isolated_env):
    old = write_claude_transcript(tmp_path, [claude_line("m1", 1, 2)],
                                  name="old.jsonl")
    snap = tmp_path / "snap.json"
    run_tool("self_usage.py", "snapshot", "--file", str(snap),
             env=isolated_env, cwd=tmp_path)
    # a newer transcript appears (new session) and wins resolution
    os.utime(old, (1_000_000_000, 1_000_000_000))
    write_claude_transcript(tmp_path, [claude_line("x1", 9, 9)],
                            name="new.jsonl")
    r = run_tool("self_usage.py", "delta", "--file", str(snap),
                 env=isolated_env, cwd=tmp_path)
    assert r.returncode == 1
    assert "TRANSCRIPT CHANGED" in r.stderr


def test_delta_mentions_self_cost_use_when_priced(tmp_path, isolated_env):
    write_claude_transcript(tmp_path, [claude_line("m1", 10, 100)])
    env = dict(isolated_env, FLEET_PROVIDERS=write_supervisor_registry(
        tmp_path, {"model": "m", "input_per_mtok": 10, "output_per_mtok": 30}))
    snap = tmp_path / "snap.json"
    run_tool("self_usage.py", "snapshot", "--file", str(snap), env=env,
             cwd=tmp_path)
    r = run_tool("self_usage.py", "delta", "--file", str(snap), env=env,
                 cwd=tmp_path)
    assert "as the measured --self-cost-usd" in r.stdout


# ---------- codex ------------------------------------------------------------

def test_codex_takes_last_cumulative_event(tmp_path, isolated_env):
    d = tmp_path / "home" / ".codex" / "sessions" / "2026" / "08"
    d.mkdir(parents=True)
    ev = lambda i, c, o: json.dumps({"payload": {"info": {"total_token_usage": {
        "input_tokens": i, "cached_input_tokens": c, "output_tokens": o}}}})
    (d / "rollout.jsonl").write_text(
        ev(100, 80, 20) + "\n" + ev(1000, 800, 200) + "\n", encoding="utf-8")
    r = run_tool("self_usage.py", "sum", "--harness", "codex",
                 env=isolated_env, cwd=tmp_path)
    assert r.returncode == 0
    assert "harness=codex" in r.stdout
    # cumulative last event; codex input includes cached -> uncached = 200
    assert "TOKENS input=200 output=200 cache_read=800 cache_write=0" in r.stdout
