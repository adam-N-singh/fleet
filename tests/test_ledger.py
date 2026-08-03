"""ledger.py: append contract, track-record summaries, pacing vs soft caps,
and true-cost dashboard accounting."""
import json
import time

from conftest import run_tool


def ledger_env(tmp_path, isolated_env):
    return dict(isolated_env, FLEET_LEDGER=str(tmp_path / "ledger.jsonl"))


def write_rows(tmp_path, rows):
    p = tmp_path / "ledger.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


NOW = int(time.time())


# ---------- append -----------------------------------------------------------

def test_append_writes_entry(tmp_path, isolated_env):
    env = ledger_env(tmp_path, isolated_env)
    r = run_tool("ledger.py", "append", "--provider", "codex", "--model", "m1",
                 "--task-type", "tests", "--outcome", "accepted",
                 "--task-id", "t-1", "--tokens", "500", env=env, cwd=tmp_path)
    assert r.returncode == 0
    assert "LOGGED codex/m1 tests -> accepted" in r.stdout
    entry = json.loads((tmp_path / "ledger.jsonl").read_text())
    assert entry["provider"] == "codex" and entry["tokens"] == 500
    assert isinstance(entry["ts"], int)


def test_append_rejects_bad_outcome(tmp_path, isolated_env):
    env = ledger_env(tmp_path, isolated_env)
    r = run_tool("ledger.py", "append", "--provider", "x", "--task-type", "t",
                 "--outcome", "sorta-worked", env=env, cwd=tmp_path)
    assert r.returncode == 2
    assert "outcome must be one of" in r.stderr


def test_append_failed_without_cost_warns(tmp_path, isolated_env):
    env = ledger_env(tmp_path, isolated_env)
    r = run_tool("ledger.py", "append", "--provider", "x", "--task-type", "t",
                 "--outcome", "failed", env=env, cwd=tmp_path)
    assert r.returncode == 0
    assert "no --cost-usd recorded" in r.stdout


def test_append_accepted_without_cost_no_warning(tmp_path, isolated_env):
    env = ledger_env(tmp_path, isolated_env)
    r = run_tool("ledger.py", "append", "--provider", "x", "--task-type", "t",
                 "--outcome", "accepted", env=env, cwd=tmp_path)
    assert "no --cost-usd" not in r.stdout


def test_append_stores_self_cost(tmp_path, isolated_env):
    env = ledger_env(tmp_path, isolated_env)
    r = run_tool("ledger.py", "append", "--provider", "codex", "--task-type", "t",
                 "--outcome", "accepted", "--self-cost-usd", "3.5",
                 env=env, cwd=tmp_path)
    assert r.returncode == 0
    entry = json.loads((tmp_path / "ledger.jsonl").read_text())
    assert entry["self_cost_usd"] == 3.5
    assert "no --self-cost-usd" not in r.stdout


def test_append_accepted_without_self_cost_nudges(tmp_path, isolated_env):
    env = ledger_env(tmp_path, isolated_env)
    r = run_tool("ledger.py", "append", "--provider", "x", "--task-type", "t",
                 "--outcome", "accepted", env=env, cwd=tmp_path)
    assert "no --self-cost-usd recorded" in r.stdout


def test_append_failed_without_self_cost_no_nudge(tmp_path, isolated_env):
    env = ledger_env(tmp_path, isolated_env)
    r = run_tool("ledger.py", "append", "--provider", "x", "--task-type", "t",
                 "--outcome", "failed", "--cost-usd", "0.1", env=env, cwd=tmp_path)
    assert "no --self-cost-usd" not in r.stdout


# ---------- summary ----------------------------------------------------------

def test_summary_empty(tmp_path, isolated_env):
    env = ledger_env(tmp_path, isolated_env)
    r = run_tool("ledger.py", "summary", env=env, cwd=tmp_path)
    assert "LEDGER EMPTY" in r.stdout


def test_summary_success_rate_and_waste(tmp_path, isolated_env):
    env = ledger_env(tmp_path, isolated_env)
    write_rows(tmp_path, [
        {"ts": NOW, "provider": "a", "model": "m", "task_type": "implement",
         "outcome": "accepted", "cost_usd": 1.0, "wall_seconds": 60},
        {"ts": NOW, "provider": "a", "model": "m", "task_type": "implement",
         "outcome": "remediated", "cost_usd": 2.0, "wall_seconds": 120},
        {"ts": NOW, "provider": "a", "model": "m", "task_type": "tests",
         "outcome": "failed", "cost_usd": 0.5, "redo_cost_usd": 0.25},
    ])
    r = run_tool("ledger.py", "summary", env=env, cwd=tmp_path)
    out = r.stdout
    assert "n=3 success=67%" in out
    assert "accepted=1 remediated=1 absorbed=0 failed=1" in out
    assert "spend=$3.5000" in out
    assert "true_cost=$3.7500" in out       # spend + redo
    assert "WASTED=$0.7500" in out          # failed cost + redo
    assert "(1 misroutes)" in out
    assert "avg_wall=90s" in out
    assert "implement: 2/2 ok" in out
    assert "tests: 0/1 ok" in out


def test_summary_realized_savings(tmp_path, isolated_env):
    env = ledger_env(tmp_path, isolated_env)
    write_rows(tmp_path, [
        # accepted with estimate: saved 3.0 - 1.0 = 2.0
        {"ts": NOW, "provider": "a", "model": "m", "task_type": "implement",
         "outcome": "accepted", "cost_usd": 1.0, "self_cost_usd": 3.0},
        # remediated with estimate: saved 2.5 - 2.0 = 0.5
        {"ts": NOW, "provider": "a", "model": "m", "task_type": "implement",
         "outcome": "remediated", "cost_usd": 2.0, "self_cost_usd": 2.5},
        # failed: misroute spend counts negative, -(0.5 + 0.25) = -0.75
        {"ts": NOW, "provider": "a", "model": "m", "task_type": "tests",
         "outcome": "failed", "cost_usd": 0.5, "redo_cost_usd": 0.25},
        # accepted without estimate: excluded from savings, not guessed
        {"ts": NOW, "provider": "a", "model": "m", "task_type": "docs",
         "outcome": "accepted", "cost_usd": 0.1},
    ])
    r = run_tool("ledger.py", "summary", env=env, cwd=tmp_path)
    out = r.stdout
    assert "SAVED=$1.7500 (3/4 est.)" in out
    assert "REALIZED SAVINGS $1.7500 (3/4 entries with estimates)" in out
    # the figure is self-describing: valuation basis is stated in the output
    assert "valued at the supervisor's researched model rates" in out
    assert "preserved quota at market value, not cash refunded" in out


def test_summary_flat_rate_savings_full_self_cost(tmp_path, isolated_env):
    # Flat-rate worker reports no dollar cost: savings = the whole self-cost.
    env = ledger_env(tmp_path, isolated_env)
    write_rows(tmp_path, [
        {"ts": NOW, "provider": "antigravity", "model": "m", "task_type": "tests",
         "outcome": "accepted", "self_cost_usd": 4.0},
    ])
    r = run_tool("ledger.py", "summary", env=env, cwd=tmp_path)
    assert "SAVED=$4.0000 (1/1 est.)" in r.stdout


def test_summary_no_estimates_no_savings_line(tmp_path, isolated_env):
    env = ledger_env(tmp_path, isolated_env)
    write_rows(tmp_path, [
        {"ts": NOW, "provider": "a", "model": "m", "task_type": "t",
         "outcome": "accepted"},
    ])
    r = run_tool("ledger.py", "summary", env=env, cwd=tmp_path)
    assert "SAVED" not in r.stdout
    assert "REALIZED SAVINGS" not in r.stdout


def test_summary_provider_filter(tmp_path, isolated_env):
    env = ledger_env(tmp_path, isolated_env)
    write_rows(tmp_path, [
        {"ts": NOW, "provider": "a", "model": "m", "task_type": "t", "outcome": "accepted"},
        {"ts": NOW, "provider": "b", "model": "m", "task_type": "t", "outcome": "failed"},
    ])
    r = run_tool("ledger.py", "summary", "--provider", "b", env=env, cwd=tmp_path)
    assert "b / m" in r.stdout and "a / m" not in r.stdout


def test_summary_skips_corrupt_lines(tmp_path, isolated_env):
    env = ledger_env(tmp_path, isolated_env)
    p = write_rows(tmp_path, [
        {"ts": NOW, "provider": "a", "model": "m", "task_type": "t", "outcome": "accepted"},
    ])
    p.write_text(p.read_text() + "{corrupt\n", encoding="utf-8")
    r = run_tool("ledger.py", "summary", env=env, cwd=tmp_path)
    assert "(1 entries)" in r.stdout


# ---------- usage (pacing vs soft caps) -------------------------------------

def usage_setup(tmp_path, isolated_env, tasks, cap_tasks):
    env = ledger_env(tmp_path, isolated_env)
    write_rows(tmp_path, [
        {"ts": NOW, "provider": "codex", "model": "m", "task_type": "t",
         "outcome": "accepted", "tokens": 100}
        for _ in range(tasks)
    ])
    reg = {"providers": {"codex": {"enabled": True, "adapter": "codex",
                                   "access": "subscription",
                                   "soft_weekly_cap": {"tasks": cap_tasks}}}}
    reg_path = tmp_path / "providers.json"
    reg_path.write_text(json.dumps(reg), encoding="utf-8")
    env["FLEET_PROVIDERS"] = str(reg_path)
    return env


def test_usage_ok_below_cap(tmp_path, isolated_env):
    env = usage_setup(tmp_path, isolated_env, tasks=2, cap_tasks=10)
    r = run_tool("ledger.py", "usage", env=env, cwd=tmp_path)
    assert "PACING tasks: 2/10 (20%) — ok" in r.stdout


def test_usage_approaching_cap(tmp_path, isolated_env):
    env = usage_setup(tmp_path, isolated_env, tasks=8, cap_tasks=10)
    r = run_tool("ledger.py", "usage", env=env, cwd=tmp_path)
    assert "approaching soft cap" in r.stdout


def test_usage_over_cap(tmp_path, isolated_env):
    env = usage_setup(tmp_path, isolated_env, tasks=12, cap_tasks=10)
    r = run_tool("ledger.py", "usage", env=env, cwd=tmp_path)
    assert "OVER SOFT CAP" in r.stdout


def test_usage_window_excludes_old_rows(tmp_path, isolated_env):
    env = ledger_env(tmp_path, isolated_env)
    write_rows(tmp_path, [
        {"ts": NOW, "provider": "a", "model": "m", "task_type": "t", "outcome": "accepted"},
        {"ts": NOW - 30 * 86400, "provider": "a", "model": "m", "task_type": "t",
         "outcome": "accepted"},
    ])
    r = run_tool("ledger.py", "usage", "--days", "7", env=env, cwd=tmp_path)
    assert "(1 dispatches)" in r.stdout


def test_usage_no_cap_configured(tmp_path, isolated_env):
    env = ledger_env(tmp_path, isolated_env)
    write_rows(tmp_path, [
        {"ts": NOW, "provider": "a", "model": "m", "task_type": "t", "outcome": "accepted"},
    ])
    r = run_tool("ledger.py", "usage", env=env, cwd=tmp_path)
    assert "no soft_weekly_cap set" in r.stdout


# ---------- dashboard --------------------------------------------------------

def test_dashboard_totals_and_waste(tmp_path, isolated_env):
    env = ledger_env(tmp_path, isolated_env)
    write_rows(tmp_path, [
        {"ts": NOW, "provider": "a", "model": "m", "task_type": "t",
         "outcome": "accepted", "cost_usd": 1.0},
        {"ts": NOW, "provider": "b", "model": "m", "task_type": "t",
         "outcome": "failed", "cost_usd": 0.4, "redo_cost_usd": 0.1},
    ])
    r = run_tool("ledger.py", "dashboard", env=env, cwd=tmp_path)
    out = r.stdout
    assert "2 dispatches" in out
    assert "TOTAL worker spend $1.4000" in out
    assert "wasted on misroutes $0.5000" in out   # failed cost + redo
    assert "true cost $1.5000" in out             # spend + redo


def test_dashboard_realized_savings(tmp_path, isolated_env):
    env = ledger_env(tmp_path, isolated_env)
    write_rows(tmp_path, [
        {"ts": NOW, "provider": "a", "model": "m", "task_type": "t",
         "outcome": "accepted", "cost_usd": 1.0, "self_cost_usd": 3.0},
        {"ts": NOW, "provider": "b", "model": "m", "task_type": "t",
         "outcome": "failed", "cost_usd": 0.4, "redo_cost_usd": 0.1},
    ])
    r = run_tool("ledger.py", "dashboard", env=env, cwd=tmp_path)
    # +2.0 from the accepted task, -0.5 from the misroute
    assert "realized savings $1.5000 (2 est., at supervisor rates)" in r.stdout


def test_dashboard_empty_window(tmp_path, isolated_env):
    env = ledger_env(tmp_path, isolated_env)
    write_rows(tmp_path, [
        {"ts": NOW - 90 * 86400, "provider": "a", "model": "m", "task_type": "t",
         "outcome": "accepted"},
    ])
    r = run_tool("ledger.py", "dashboard", "--days", "14", env=env, cwd=tmp_path)
    assert "0 dispatches" in r.stdout
