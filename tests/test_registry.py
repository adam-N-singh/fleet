"""registry.py: resolution order, field access, listing, validation."""
import json

from conftest import run_tool


def write_registry(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


MINIMAL = {
    "providers": {
        "codex": {
            "enabled": True,
            "adapter": "codex",
            "access": "subscription",
            "default_model": "",
            "cost": {"mode": "flat"},
        },
        "parked": {
            "enabled": False,
            "adapter": "opencode",
            "access": "api",
            "default_model": "deepseek/deepseek-chat",
        },
    },
    "routing": {"prefer_order": ["codex"]},
}


# ---------- resolution order -------------------------------------------------

def test_path_none_found(tmp_path, isolated_env):
    r = run_tool("registry.py", "path", env=isolated_env, cwd=tmp_path)
    assert r.returncode == 1
    assert "no providers.json" in r.stderr


def test_path_project_level(tmp_path, isolated_env):
    write_registry(tmp_path / ".fleet" / "providers.json", MINIMAL)
    r = run_tool("registry.py", "path", env=isolated_env, cwd=tmp_path)
    assert r.returncode == 0
    assert ".fleet" in r.stdout


def test_path_user_level_fallback(tmp_path, isolated_env):
    home = tmp_path / "home"  # created by the fixture
    write_registry(home / ".fleet" / "providers.json", MINIMAL)
    r = run_tool("registry.py", "path", env=isolated_env, cwd=tmp_path)
    assert r.returncode == 0
    assert "home" in r.stdout


def test_path_env_var_wins(tmp_path, isolated_env):
    write_registry(tmp_path / ".fleet" / "providers.json", MINIMAL)
    explicit = tmp_path / "elsewhere.json"
    write_registry(explicit, MINIMAL)
    env = dict(isolated_env, FLEET_PROVIDERS=str(explicit))
    r = run_tool("registry.py", "path", env=env, cwd=tmp_path)
    assert r.returncode == 0
    assert "elsewhere.json" in r.stdout


def test_malformed_json_exits_2(tmp_path, isolated_env):
    p = tmp_path / ".fleet" / "providers.json"
    p.parent.mkdir(parents=True)
    p.write_text("{not json", encoding="utf-8")
    r = run_tool("registry.py", "path", env=isolated_env, cwd=tmp_path)
    assert r.returncode == 2
    assert "could not parse" in r.stderr


# ---------- get --------------------------------------------------------------

def test_get_simple_and_nested(tmp_path, isolated_env):
    write_registry(tmp_path / ".fleet" / "providers.json", MINIMAL)
    r = run_tool("registry.py", "get", "codex", "adapter", env=isolated_env, cwd=tmp_path)
    assert r.returncode == 0 and r.stdout.strip() == "codex"
    r = run_tool("registry.py", "get", "codex", "cost.mode", env=isolated_env, cwd=tmp_path)
    assert r.stdout.strip() == "flat"


def test_get_bool_prints_lowercase(tmp_path, isolated_env):
    write_registry(tmp_path / ".fleet" / "providers.json", MINIMAL)
    r = run_tool("registry.py", "get", "codex", "enabled", env=isolated_env, cwd=tmp_path)
    assert r.stdout.strip() == "true"
    r = run_tool("registry.py", "get", "parked", "enabled", env=isolated_env, cwd=tmp_path)
    assert r.stdout.strip() == "false"


def test_get_default_for_missing_field(tmp_path, isolated_env):
    write_registry(tmp_path / ".fleet" / "providers.json", MINIMAL)
    r = run_tool("registry.py", "get", "codex", "max_workers", "2",
                 env=isolated_env, cwd=tmp_path)
    assert r.returncode == 0 and r.stdout.strip() == "2"


def test_get_unknown_provider_exits_1(tmp_path, isolated_env):
    write_registry(tmp_path / ".fleet" / "providers.json", MINIMAL)
    r = run_tool("registry.py", "get", "nope", "adapter", env=isolated_env, cwd=tmp_path)
    assert r.returncode == 1
    assert "not in registry" in r.stderr


def test_get_dict_prints_json(tmp_path, isolated_env):
    write_registry(tmp_path / ".fleet" / "providers.json", MINIMAL)
    r = run_tool("registry.py", "get", "codex", "cost", env=isolated_env, cwd=tmp_path)
    assert json.loads(r.stdout) == {"mode": "flat"}


# ---------- list -------------------------------------------------------------

def test_list_shows_order_and_disabled(tmp_path, isolated_env):
    write_registry(tmp_path / ".fleet" / "providers.json", MINIMAL)
    r = run_tool("registry.py", "list", env=isolated_env, cwd=tmp_path)
    assert r.returncode == 0
    assert "PREFER_ORDER codex" in r.stdout
    assert "parked: DISABLED" in r.stdout
    assert "adapter=codex" in r.stdout


def test_list_flags_review_due(tmp_path, isolated_env):
    data = json.loads(json.dumps(MINIMAL))
    data["providers"]["codex"]["review_after"] = "2000-01-01"
    write_registry(tmp_path / ".fleet" / "providers.json", data)
    r = run_tool("registry.py", "list", env=isolated_env, cwd=tmp_path)
    assert "REVIEW_DUE" in r.stdout


def test_list_future_review_not_flagged(tmp_path, isolated_env):
    data = json.loads(json.dumps(MINIMAL))
    data["providers"]["codex"]["review_after"] = "2999-01-01"
    write_registry(tmp_path / ".fleet" / "providers.json", data)
    r = run_tool("registry.py", "list", env=isolated_env, cwd=tmp_path)
    assert "review_after: 2999-01-01" in r.stdout
    assert "REVIEW_DUE" not in r.stdout


def test_list_shows_supervisor_rates(tmp_path, isolated_env):
    data = json.loads(json.dumps(MINIMAL))
    data["supervisor"] = {"model": "claude-fable-5", "input_per_mtok": 5,
                          "output_per_mtok": 25, "notes": "pricing verified 2026-08"}
    write_registry(tmp_path / ".fleet" / "providers.json", data)
    r = run_tool("registry.py", "list", env=isolated_env, cwd=tmp_path)
    assert ("SUPERVISOR model=claude-fable-5 rates in $5/Mtok, out $25/Mtok "
            "— pricing verified 2026-08") in r.stdout


def test_list_nudges_when_supervisor_rates_missing(tmp_path, isolated_env):
    write_registry(tmp_path / ".fleet" / "providers.json", MINIMAL)
    r = run_tool("registry.py", "list", env=isolated_env, cwd=tmp_path)
    assert "SUPERVISOR rates not set" in r.stdout


# ---------- validate ---------------------------------------------------------

def test_validate_ok_counts_enabled(tmp_path, isolated_env):
    write_registry(tmp_path / ".fleet" / "providers.json", MINIMAL)
    r = run_tool("registry.py", "validate", env=isolated_env, cwd=tmp_path)
    assert r.returncode == 0
    assert "(1 enabled)" in r.stdout


def test_validate_unknown_adapter(tmp_path, isolated_env):
    data = json.loads(json.dumps(MINIMAL))
    data["providers"]["codex"]["adapter"] = "hal9000"
    write_registry(tmp_path / ".fleet" / "providers.json", data)
    r = run_tool("registry.py", "validate", env=isolated_env, cwd=tmp_path)
    assert r.returncode == 1
    assert "unknown adapter 'hal9000'" in r.stdout


def test_validate_bad_access_mode(tmp_path, isolated_env):
    data = json.loads(json.dumps(MINIMAL))
    data["providers"]["codex"]["access"] = "gratis"
    write_registry(tmp_path / ".fleet" / "providers.json", data)
    r = run_tool("registry.py", "validate", env=isolated_env, cwd=tmp_path)
    assert r.returncode == 1
    assert "access should be one of" in r.stdout


def test_validate_enabled_opencode_needs_model(tmp_path, isolated_env):
    data = json.loads(json.dumps(MINIMAL))
    data["providers"]["parked"]["enabled"] = True
    data["providers"]["parked"]["default_model"] = ""
    write_registry(tmp_path / ".fleet" / "providers.json", data)
    r = run_tool("registry.py", "validate", env=isolated_env, cwd=tmp_path)
    assert r.returncode == 1
    assert "requires default_model" in r.stdout


def test_validate_disabled_opencode_without_model_is_fine(tmp_path, isolated_env):
    data = json.loads(json.dumps(MINIMAL))
    data["providers"]["parked"]["default_model"] = ""  # still disabled
    write_registry(tmp_path / ".fleet" / "providers.json", data)
    r = run_tool("registry.py", "validate", env=isolated_env, cwd=tmp_path)
    assert r.returncode == 0


def test_validate_prefer_order_unknown_provider(tmp_path, isolated_env):
    data = json.loads(json.dumps(MINIMAL))
    data["routing"]["prefer_order"] = ["codex", "ghost"]
    write_registry(tmp_path / ".fleet" / "providers.json", data)
    r = run_tool("registry.py", "validate", env=isolated_env, cwd=tmp_path)
    assert r.returncode == 1
    assert "unknown provider 'ghost'" in r.stdout


def test_validate_soft_cap_shape(tmp_path, isolated_env):
    data = json.loads(json.dumps(MINIMAL))
    data["providers"]["codex"]["soft_weekly_cap"] = {"requests": 10}  # wrong key
    write_registry(tmp_path / ".fleet" / "providers.json", data)
    r = run_tool("registry.py", "validate", env=isolated_env, cwd=tmp_path)
    assert r.returncode == 1
    assert "soft_weekly_cap" in r.stdout


def test_validate_supervisor_needs_numeric_rates(tmp_path, isolated_env):
    data = json.loads(json.dumps(MINIMAL))
    data["supervisor"] = {"model": "m", "input_per_mtok": "cheap"}  # non-numeric, missing output
    write_registry(tmp_path / ".fleet" / "providers.json", data)
    r = run_tool("registry.py", "validate", env=isolated_env, cwd=tmp_path)
    assert r.returncode == 1
    assert "supervisor block needs numeric" in r.stdout


def test_validate_supervisor_ok_and_absent_ok(tmp_path, isolated_env):
    data = json.loads(json.dumps(MINIMAL))
    data["supervisor"] = {"model": "m", "input_per_mtok": 5, "output_per_mtok": 25}
    write_registry(tmp_path / ".fleet" / "providers.json", data)
    r = run_tool("registry.py", "validate", env=isolated_env, cwd=tmp_path)
    assert r.returncode == 0
    # absent block stays valid — the field is optional
    write_registry(tmp_path / ".fleet" / "providers.json", MINIMAL)
    r = run_tool("registry.py", "validate", env=isolated_env, cwd=tmp_path)
    assert r.returncode == 0
