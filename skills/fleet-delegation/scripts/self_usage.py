#!/usr/bin/env python3
"""Measure the supervisor's OWN session token usage from the harness's session
transcript, and price it at the registry's supervisor rates. This turns
self-cost from a parity guess into a measurement: snapshot before a span of
work, delta after, and the priced difference is what that span actually cost
in-session.

Usage:
  self_usage.py sum      [--harness auto|claude|codex] [--cwd P] [--transcript P]
  self_usage.py snapshot [same options] [--file P]     record current totals
  self_usage.py delta    [same options] [--file P]     totals since snapshot

Harness sources (auto tries in this order):
  claude   newest ~/.claude/projects/<cwd-slug>/*.jsonl — per-turn usage
           blocks, deduplicated by message id, summed. Exact.
  codex    newest ~/.codex/sessions/**/*.jsonl — last cumulative
           total_token_usage event. Approximate field mapping.
Override with --transcript (or $FLEET_SELF_TRANSCRIPT) when resolution guesses
wrong. If no source is found, exit 1 — fall back to the parity estimate.

Pricing uses the registry's top-level supervisor block (input_per_mtok,
output_per_mtok, and optional cache_read_per_mtok / cache_write_per_mtok;
when the cache rates are absent they are assumed from the input rate:
read = input/10, write = input*1.25).

Typical flow:
  snapshot at dispatch (or before absorbing a task) -> work -> delta.
  delta's COST_USD is the measured --self-cost-usd for an absorbed span, or
  the measured supervision overhead for a dispatch span.
"""
import argparse
import glob
import json
import os
import re
import sys
import time

FIELDS = ("input", "output", "cache_read", "cache_write")
SNAPSHOT_DEFAULT = os.path.join(".fleet-runs", "self-usage-snapshot.json")


def home():
    return os.path.expanduser("~")


def cwd_slug(cwd):
    """Claude Code project-dir slug: every non-alphanumeric char becomes '-'."""
    return re.sub(r"[^A-Za-z0-9-]", "-", os.path.abspath(cwd))


def newest(paths):
    paths = [p for p in paths if os.path.isfile(p)]
    return max(paths, key=os.path.getmtime) if paths else None


def read_claude(path):
    """Sum per-turn usage blocks, deduped by message id (a streamed message
    can span several transcript lines carrying cumulative usage — the last
    line per id has the final counts)."""
    per_msg = {}
    fallback_idx = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = rec.get("message") or {}
            u = msg.get("usage")
            if not isinstance(u, dict):
                continue
            key = msg.get("id")
            if not key:
                key = f"_line{fallback_idx}"
                fallback_idx += 1
            per_msg[key] = u
    tot = dict.fromkeys(FIELDS, 0)
    for u in per_msg.values():
        tot["input"] += u.get("input_tokens", 0) or 0
        tot["output"] += u.get("output_tokens", 0) or 0
        tot["cache_read"] += u.get("cache_read_input_tokens", 0) or 0
        tot["cache_write"] += u.get("cache_creation_input_tokens", 0) or 0
    return tot, len(per_msg)


def read_codex(path):
    """Take the last cumulative total_token_usage event. Codex counts cached
    tokens inside input_tokens, so uncached input = input - cached."""
    last = None
    events = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            info = (rec.get("payload") or {}).get("info") or {}
            u = info.get("total_token_usage")
            if isinstance(u, dict):
                last = u
                events += 1
    tot = dict.fromkeys(FIELDS, 0)
    if last:
        cached = last.get("cached_input_tokens", 0) or 0
        tot["input"] = max(0, (last.get("input_tokens", 0) or 0) - cached)
        tot["cache_read"] = cached
        tot["output"] = last.get("output_tokens", 0) or 0
    return tot, events


def resolve(harness, cwd, transcript):
    """Return (harness, transcript_path, totals, turns) or None."""
    if transcript:
        h = harness if harness != "auto" else (
            "codex" if os.sep + ".codex" + os.sep in transcript
            or "/.codex/" in transcript else "claude")
        reader = read_codex if h == "codex" else read_claude
        tot, turns = reader(transcript)
        return h, transcript, tot, turns
    candidates = []
    if harness in ("auto", "claude"):
        candidates.append(("claude", os.path.join(
            home(), ".claude", "projects", cwd_slug(cwd), "*.jsonl"), read_claude))
    if harness in ("auto", "codex"):
        candidates.append(("codex", os.path.join(
            home(), ".codex", "sessions", "**", "*.jsonl"), read_codex))
    for h, pattern, reader in candidates:
        path = newest(glob.glob(pattern, recursive=True))
        if path:
            tot, turns = reader(path)
            return h, path, tot, turns
    return None


def supervisor_rates():
    """Best-effort read of the registry's supervisor block; never fatal."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import registry as reg
        path = reg.find_registry()
        if path:
            with open(path, encoding="utf-8") as f:
                sup = json.load(f).get("supervisor")
            if isinstance(sup, dict) and all(
                    isinstance(sup.get(k), (int, float))
                    for k in ("input_per_mtok", "output_per_mtok")):
                return sup
    except Exception:
        pass
    return None


def price(tot, sup):
    ipm = sup["input_per_mtok"]
    opm = sup["output_per_mtok"]
    assumed = not all(isinstance(sup.get(k), (int, float))
                      for k in ("cache_read_per_mtok", "cache_write_per_mtok"))
    crm = sup.get("cache_read_per_mtok")
    cwm = sup.get("cache_write_per_mtok")
    crm = crm if isinstance(crm, (int, float)) else ipm * 0.1
    cwm = cwm if isinstance(cwm, (int, float)) else ipm * 1.25
    usd = (tot["input"] * ipm + tot["output"] * opm
           + tot["cache_read"] * crm + tot["cache_write"] * cwm) / 1e6
    rates = (f"in ${ipm}/Mtok, out ${opm}/Mtok, cache_read ${crm:g}/Mtok, "
             f"cache_write ${cwm:g}/Mtok")
    if assumed:
        rates += " — cache rates assumed from input rate"
    return usd, rates


def print_report(h, path, tot, turns, label="SELF_USAGE"):
    print(f"{label} harness={h}")
    print(f"TRANSCRIPT {path}")
    print(f"TURNS {turns}")
    print("TOKENS " + " ".join(f"{k}={tot[k]}" for k in FIELDS))
    sup = supervisor_rates()
    if sup:
        usd, rates = price(tot, sup)
        print(f"COST_USD {usd:.4f} ({rates})")
        return usd
    print("COST_USD unavailable — no supervisor rates in registry "
          "(add a supervisor block: /fleet-init)")
    return None


def main():
    ap = argparse.ArgumentParser(add_help=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("sum", "snapshot", "delta"):
        p = sub.add_parser(name)
        p.add_argument("--harness", choices=("auto", "claude", "codex"),
                       default="auto")
        p.add_argument("--cwd", default=os.getcwd())
        p.add_argument("--transcript",
                       default=os.environ.get("FLEET_SELF_TRANSCRIPT") or None)
        if name in ("snapshot", "delta"):
            p.add_argument("--file", default=SNAPSHOT_DEFAULT)
    args = ap.parse_args()

    got = resolve(args.harness, args.cwd, args.transcript)
    if not got:
        print("NO TRANSCRIPT found for this session (harness="
              f"{args.harness}) — cannot measure self-usage; fall back to the "
              "parity estimate (worker tokens at supervisor rates).",
              file=sys.stderr)
        return 1
    h, path, tot, turns = got

    if args.cmd == "sum":
        print_report(h, path, tot, turns)
        return 0

    if args.cmd == "snapshot":
        os.makedirs(os.path.dirname(args.file) or ".", exist_ok=True)
        with open(args.file, "w", encoding="utf-8") as f:
            json.dump({"ts": int(time.time()), "harness": h,
                       "transcript": path, "turns": turns, "totals": tot}, f)
        print(f"SNAPSHOT {args.file}")
        print("TOKENS " + " ".join(f"{k}={tot[k]}" for k in FIELDS))
        return 0

    # delta
    if not os.path.isfile(args.file):
        print(f"NO SNAPSHOT at {args.file} — run `self_usage.py snapshot` "
              "before the span you want to measure.", file=sys.stderr)
        return 1
    with open(args.file, encoding="utf-8") as f:
        snap = json.load(f)
    if snap.get("transcript") != path:
        print("TRANSCRIPT CHANGED since snapshot (was "
              f"{snap.get('transcript')}) — delta would mix sessions; take a "
              "fresh snapshot.", file=sys.stderr)
        return 1
    d = {k: tot[k] - (snap.get("totals", {}).get(k, 0) or 0) for k in FIELDS}
    if any(v < 0 for v in d.values()):
        print("NEGATIVE DELTA — the transcript shrank (session restarted?); "
              "take a fresh snapshot.", file=sys.stderr)
        return 1
    age = int(time.time()) - (snap.get("ts") or 0)
    print(f"SINCE snapshot {age // 60}m{age % 60}s ago")
    usd = print_report(h, path, d, turns - (snap.get("turns") or 0),
                       label="SELF_USAGE_DELTA")
    if usd is not None:
        print("Use COST_USD as the measured --self-cost-usd when this span "
              "was one absorbed task, or as the supervision overhead when it "
              "was a dispatch round-trip.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
