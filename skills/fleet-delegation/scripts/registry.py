#!/usr/bin/env python3
"""Read the fleet provider registry (providers.json).

Usage:
  registry.py path                          print resolved registry path (exit 1 if none)
  registry.py list                          human/agent-readable summary of enabled providers
  registry.py get <provider> <field> [dflt] print one field (dots for nesting, e.g. cost.mode)
  registry.py validate                      check schema basics, report problems

Registry resolution order:
  1. $FLEET_PROVIDERS (explicit path)
  2. ./.fleet/providers.json   (project-level)
  3. ~/.fleet/providers.json   (user-level)
"""
import json
import os
import sys

SEARCH = [
    os.environ.get("FLEET_PROVIDERS", ""),
    os.path.join(".fleet", "providers.json"),
    os.path.expanduser("~/.fleet/providers.json"),
]

KNOWN_ADAPTERS = {"codex", "antigravity", "gemini", "opencode", "claude",
                  "grok", "cursor", "copilot", "qwen", "droid", "amp"}
ACCESS_MODES = {"subscription", "api", "local", "free"}


def find_registry():
    for p in SEARCH:
        if p and os.path.isfile(p):
            return p
    return None


def load():
    p = find_registry()
    if not p:
        return None, None
    try:
        with open(p, encoding="utf-8") as f:
            return p, json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: could not parse {p}: {e}", file=sys.stderr)
        sys.exit(2)


def get_nested(d, dotted, default=None):
    cur = d
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def main():
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    cmd = sys.argv[1]
    path, data = load()

    if cmd == "path":
        if path:
            print(path)
            return 0
        print("ERROR: no providers.json found (searched $FLEET_PROVIDERS, ./.fleet/, ~/.fleet/). "
              "Run /fleet-init or copy config/providers.example.json.", file=sys.stderr)
        return 1

    if data is None:
        print("ERROR: no providers.json found. Run /fleet-init to create one.", file=sys.stderr)
        return 1

    providers = data.get("providers", {})

    if cmd == "get":
        if len(sys.argv) < 4:
            print("usage: registry.py get <provider> <field> [default]", file=sys.stderr)
            return 2
        name, field = sys.argv[2], sys.argv[3]
        default = sys.argv[4] if len(sys.argv) > 4 else ""
        prov = providers.get(name)
        if prov is None:
            print(f"ERROR: provider '{name}' not in registry", file=sys.stderr)
            return 1
        val = get_nested(prov, field, default)
        if isinstance(val, (dict, list)):
            print(json.dumps(val))
        elif isinstance(val, bool):
            print("true" if val else "false")
        else:
            print(val)
        return 0

    if cmd == "list":
        print(f"REGISTRY {path}")
        order = data.get("routing", {}).get("prefer_order", [])
        if order:
            print(f"PREFER_ORDER {' > '.join(order)}")
        sup = data.get("supervisor")
        if isinstance(sup, dict):
            print(f"SUPERVISOR model={sup.get('model', '?')} "
                  f"rates in ${sup.get('input_per_mtok', '?')}/Mtok, "
                  f"out ${sup.get('output_per_mtok', '?')}/Mtok"
                  + (f" — {sup['notes']}" if sup.get("notes") else ""))
        else:
            print("SUPERVISOR rates not set — self-cost and realized-savings "
                  "estimates need researched pricing for the supervisor's own "
                  "model (run /fleet-init or add a top-level 'supervisor' block)")
        for name, p in providers.items():
            if not p.get("enabled", False):
                print(f"\n{name}: DISABLED")
                continue
            cost = p.get("cost", {})
            cost_s = cost.get("mode", "?")
            if cost_s == "per_token":
                cost_s += (f" (in ${cost.get('input_per_mtok', '?')}/Mtok, "
                           f"out ${cost.get('output_per_mtok', '?')}/Mtok)")
            print(f"\n{name}: adapter={p.get('adapter', '?')} "
                  f"model={p.get('default_model') or '(cli default)'} "
                  f"access={p.get('access', '?')} cost={cost_s} "
                  f"max_workers={p.get('max_workers', 2)} trust={p.get('trust', 'standard')}")
            for k in ("strengths", "weaknesses"):
                v = p.get(k)
                if v:
                    print(f"  {k}: {'; '.join(v) if isinstance(v, list) else v}")
            if p.get("context_window"):
                print(f"  context_window: {p['context_window']}")
            cap = p.get("soft_weekly_cap")
            if cap:
                print(f"  soft_weekly_cap: {json.dumps(cap)} (check pacing: ledger.py usage)")
            ra = p.get("review_after")
            if ra:
                import datetime
                try:
                    due = datetime.date.fromisoformat(ra) < datetime.date.today()
                except ValueError:
                    due = False
                print(f"  review_after: {ra}" + ("  ** REVIEW_DUE — access terms may have changed; re-run /fleet-init for this provider and update caps/cost **" if due else ""))
            if p.get("notes"):
                print(f"  notes: {p['notes']}")
        return 0

    if cmd == "validate":
        problems = []
        if not providers:
            problems.append("no 'providers' object")
        for name, p in providers.items():
            if p.get("adapter") not in KNOWN_ADAPTERS:
                problems.append(f"{name}: unknown adapter '{p.get('adapter')}' "
                                f"(known: {sorted(KNOWN_ADAPTERS)})")
            if p.get("access") not in ACCESS_MODES:
                problems.append(f"{name}: access should be one of {sorted(ACCESS_MODES)}")
            cap = p.get("soft_weekly_cap")
            if cap is not None:
                if not isinstance(cap, dict) or not any(
                        isinstance(cap.get(k), (int, float)) for k in ("tasks", "tokens")):
                    problems.append(f"{name}: soft_weekly_cap must be an object with "
                                    f"numeric 'tasks' and/or 'tokens'")
            if p.get("adapter") == "opencode" and p.get("enabled") and not p.get("default_model"):
                problems.append(f"{name}: opencode adapter requires default_model "
                                f"in provider/model form (e.g. deepseek/deepseek-chat)")
        for name in data.get("routing", {}).get("prefer_order", []):
            if name not in providers:
                problems.append(f"routing.prefer_order references unknown provider '{name}'")
        sup = data.get("supervisor")
        if sup is not None:
            if not isinstance(sup, dict) or not all(
                    isinstance(sup.get(k), (int, float))
                    for k in ("input_per_mtok", "output_per_mtok")):
                problems.append("supervisor block needs numeric input_per_mtok and "
                                "output_per_mtok (researched rates, not guesses)")
        if problems:
            for p in problems:
                print(f"PROBLEM {p}")
            return 1
        print(f"OK {path} ({sum(1 for p in providers.values() if p.get('enabled'))} enabled)")
        return 0

    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
