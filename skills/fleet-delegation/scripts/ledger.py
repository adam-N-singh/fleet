#!/usr/bin/env python3
"""Fleet outcome ledger: record what each worker actually delivered, and
summarize track records, usage pacing, and true costs so routing decisions
learn from observed results.

Usage:
  ledger.py append --provider P --model M --task-type T --outcome O
                   [--task-id ID] [--cost-usd X] [--redo-cost-usd Y]
                   [--tokens N] [--wall-seconds S] [--notes "..."]
  ledger.py summary [--provider P]
  ledger.py usage [--provider P] [--days 7]     dispatch volume vs soft caps
  ledger.py dashboard [--days 14]               spend by provider by day

Outcomes:
  accepted     passed verification on the first round
  remediated   passed after one or more resume/fix rounds
  absorbed     supervisor took the task back and did it itself
  failed       worker errored out or was abandoned

Cost fields (true-cost accounting):
  --cost-usd        what the worker spent — LOG THIS EVEN FOR absorbed/failed;
                    wasted spend is real spend and must count against the
                    provider's track record
  --redo-cost-usd   what redoing the task cost after an absorb/fail, when
                    known (e.g. a replacement worker's cost). Optional.

Task types (free-form, but keep them consistent): implement, tests, refactor,
migration, lint-fix, docs, boilerplate, review, other.

Ledger path: $FLEET_LEDGER, else .fleet-runs/ledger.jsonl (project-local).
"""
import argparse
import json
import os
import sys
import time
from collections import defaultdict

OUTCOMES = {"accepted", "remediated", "absorbed", "failed"}


def ledger_path():
    return os.environ.get("FLEET_LEDGER") or os.path.join(".fleet-runs", "ledger.jsonl")


def load_rows():
    path = ledger_path()
    if not os.path.isfile(path):
        return path, []
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return path, rows


def load_registry():
    """Best-effort read of providers.json for soft caps; never fatal."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import registry as reg
        path = reg.find_registry()
        if path:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return None


def fnum(v):
    return isinstance(v, (int, float))


def cmd_append(args):
    if args.outcome not in OUTCOMES:
        print(f"ERROR: outcome must be one of {sorted(OUTCOMES)}", file=sys.stderr)
        return 2
    entry = {
        "ts": int(time.time()),
        "provider": args.provider,
        "model": args.model,
        "task_type": args.task_type,
        "outcome": args.outcome,
    }
    for k in ("task_id", "cost_usd", "redo_cost_usd", "tokens", "wall_seconds", "notes"):
        v = getattr(args, k)
        if v is not None:
            entry[k] = v
    path = ledger_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"LOGGED {entry['provider']}/{entry['model'] or '?'} "
          f"{entry['task_type']} -> {entry['outcome']}")
    if args.outcome in ("absorbed", "failed") and args.cost_usd is None:
        print("NOTE no --cost-usd recorded for this wasted dispatch. If the worker "
              "reported cost or tokens, log it — wasted spend must count against "
              "the provider's true cost.")
    return 0


def cmd_summary(args):
    path, rows = load_rows()
    if not rows:
        print("LEDGER EMPTY (no outcomes recorded yet — routing has no track "
              "record to draw on; rely on the registry and cost cascade)")
        return 0
    if args.provider:
        rows = [r for r in rows if r.get("provider") == args.provider]
    if not rows:
        print("LEDGER EMPTY for that filter")
        return 0

    groups = defaultdict(list)
    for r in rows:
        groups[(r.get("provider", "?"), r.get("model") or "(default)")].append(r)

    print(f"LEDGER {path} ({len(rows)} entries)")
    for (prov, model), items in sorted(groups.items()):
        n = len(items)
        counts = defaultdict(int)
        for r in items:
            counts[r.get("outcome", "?")] += 1
        ok = counts["accepted"] + counts["remediated"]
        rate = f"{100 * ok / n:.0f}%"
        costs = [r["cost_usd"] for r in items if fnum(r.get("cost_usd"))]
        redos = [r["redo_cost_usd"] for r in items if fnum(r.get("redo_cost_usd"))]
        wasted = [r["cost_usd"] for r in items
                  if r.get("outcome") in ("absorbed", "failed") and fnum(r.get("cost_usd"))]
        walls = [r["wall_seconds"] for r in items if fnum(r.get("wall_seconds"))]
        line = (f"\n{prov} / {model}: n={n} success={rate} "
                f"(accepted={counts['accepted']} remediated={counts['remediated']} "
                f"absorbed={counts['absorbed']} failed={counts['failed']})")
        if costs:
            true_total = sum(costs) + sum(redos)
            line += f" spend=${sum(costs):.4f} true_cost=${true_total:.4f}"
        if wasted or redos:
            line += (f" WASTED=${sum(wasted) + sum(redos):.4f} "
                     f"({counts['absorbed'] + counts['failed']} misroutes)")
        if walls:
            line += f" avg_wall={sum(walls) / len(walls):.0f}s"
        print(line)
        by_type = defaultdict(lambda: [0, 0])
        for r in items:
            t = r.get("task_type", "other")
            by_type[t][1] += 1
            if r.get("outcome") in ("accepted", "remediated"):
                by_type[t][0] += 1
        for t, (tok, tn) in sorted(by_type.items()):
            print(f"  {t}: {tok}/{tn} ok")
    return 0


def cap_status(pct):
    if pct >= 100:
        return "OVER SOFT CAP — treat as a soft cooldown: route elsewhere unless no capable alternative"
    if pct >= 70:
        return "approaching soft cap — deprioritize in the cascade"
    return "ok"


def cmd_usage(args):
    path, rows = load_rows()
    cutoff = int(time.time()) - args.days * 86400
    rows = [r for r in rows if r.get("ts", 0) >= cutoff]
    if args.provider:
        rows = [r for r in rows if r.get("provider") == args.provider]
    reg = load_registry() or {}
    reg_providers = reg.get("providers", {})

    print(f"USAGE last {args.days}d ({len(rows)} dispatches) — pacing proxy: "
          f"counts DELEGATED work only, not the supervisor's own session usage")
    if not rows:
        print("(no dispatches in window)")
        return 0

    by_prov = defaultdict(list)
    for r in rows:
        by_prov[r.get("provider", "?")].append(r)

    for prov, items in sorted(by_prov.items()):
        tasks = len(items)
        tokens = sum(r["tokens"] for r in items if fnum(r.get("tokens")))
        cost = sum(r["cost_usd"] for r in items if fnum(r.get("cost_usd")))
        line = f"\n{prov}: {tasks} tasks, {tokens} tokens, ${cost:.4f}"
        print(line)
        cap = (reg_providers.get(prov) or {}).get("soft_weekly_cap") or {}
        shown = False
        if fnum(cap.get("tasks")) and cap["tasks"] > 0:
            pct = 100 * tasks / cap["tasks"]
            print(f"  PACING tasks: {tasks}/{cap['tasks']} ({pct:.0f}%) — {cap_status(pct)}")
            shown = True
        if fnum(cap.get("tokens")) and cap["tokens"] > 0:
            pct = 100 * tokens / cap["tokens"]
            print(f"  PACING tokens: {tokens}/{cap['tokens']} ({pct:.0f}%) — {cap_status(pct)}")
            shown = True
        if not shown:
            print("  PACING no soft_weekly_cap set in registry")
    return 0


def cmd_dashboard(args):
    path, rows = load_rows()
    cutoff = int(time.time()) - args.days * 86400
    rows = [r for r in rows if r.get("ts", 0) >= cutoff]
    print(f"DASHBOARD last {args.days}d — {len(rows)} dispatches ({path})")
    if not rows:
        return 0

    by_day = defaultdict(lambda: defaultdict(lambda: [0, 0.0]))  # day -> prov -> [n, cost]
    total_cost = 0.0
    total_redo = 0.0
    wasted = 0.0
    misroutes = 0
    for r in rows:
        day = time.strftime("%Y-%m-%d", time.localtime(r.get("ts", 0)))
        prov = r.get("provider", "?")
        c = r["cost_usd"] if fnum(r.get("cost_usd")) else 0.0
        by_day[day][prov][0] += 1
        by_day[day][prov][1] += c
        total_cost += c
        if fnum(r.get("redo_cost_usd")):
            total_redo += r["redo_cost_usd"]
        if r.get("outcome") in ("absorbed", "failed"):
            misroutes += 1
            wasted += c
    for day in sorted(by_day):
        parts = [f"{p}: {n} (${c:.4f})" for p, (n, c) in sorted(by_day[day].items())]
        print(f"{day}  " + "  ".join(parts))
    print(f"\nTOTAL worker spend ${total_cost:.4f}"
          f" | wasted on misroutes ${wasted + total_redo:.4f}"
          f" ({misroutes} tasks{', incl redo $%.4f' % total_redo if total_redo else ''})"
          f" | true cost ${total_cost + total_redo:.4f}")
    print("Flat-rate/subscription dispatches show $0 — their budget signal is the "
          "PACING view (ledger.py usage), not dollars.")
    return 0


def main():
    ap = argparse.ArgumentParser(add_help=True)
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("append")
    a.add_argument("--provider", required=True)
    a.add_argument("--model", default="")
    a.add_argument("--task-type", required=True)
    a.add_argument("--outcome", required=True)
    a.add_argument("--task-id", default=None)
    a.add_argument("--cost-usd", type=float, default=None)
    a.add_argument("--redo-cost-usd", type=float, default=None)
    a.add_argument("--tokens", type=int, default=None)
    a.add_argument("--wall-seconds", type=int, default=None)
    a.add_argument("--notes", default=None)

    s = sub.add_parser("summary")
    s.add_argument("--provider", default=None)

    u = sub.add_parser("usage")
    u.add_argument("--provider", default=None)
    u.add_argument("--days", type=int, default=7)

    d = sub.add_parser("dashboard")
    d.add_argument("--days", type=int, default=14)

    args = ap.parse_args()
    return {"append": cmd_append, "summary": cmd_summary,
            "usage": cmd_usage, "dashboard": cmd_dashboard}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
