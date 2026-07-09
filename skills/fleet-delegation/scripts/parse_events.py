#!/usr/bin/env python3
"""Parse worker output into uniform fields, across adapter formats.

Usage: parse_events.py <output-file> <field> --format codex|opencode|gemini|claude

Fields:
  session     worker session id (empty if the format has none)
  final       text of the final agent message / response
  usage       token/cost JSON (shape varies by provider; ledger-ready)
  last_event  most recent event type (streaming formats only)
  errors      error events / error field, one JSON object per line
  completed   "yes" if the run produced a completed result

Deliberately tolerant of schema drift between CLI versions: unparseable
lines are skipped, multiple key spellings are accepted, and unknown event
shapes degrade to empty output (exit 1) rather than crashing.
"""
import json
import sys


def load_jsonl(path):
    events = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return None
    return events


def load_object(path):
    """Gemini --output-format json: one JSON object, possibly with stray
    log lines around it. Try whole-buffer parse, then first-brace slice."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            buf = f.read()
    except OSError:
        return None
    for candidate in (buf, buf[buf.find("{"):] if "{" in buf else ""):
        if not candidate:
            continue
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    return None


def find_key(obj, names, _depth=0):
    """Recursively find the first value under any of the given key names."""
    if _depth > 6:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in names and v:
                return v
            found = find_key(v, names, _depth + 1)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = find_key(item, names, _depth + 1)
            if found:
                return found
    return None


SESSION_KEYS = {"thread_id", "session_id", "sessionID", "sessionId", "id"}


def codex(events, field):
    if field == "session":
        for e in events:
            if e.get("type") == "thread.started":
                sid = e.get("thread_id") or e.get("session_id") or (e.get("thread") or {}).get("id")
                if sid:
                    return str(sid)
    if field == "final":
        texts = [e["item"]["text"] for e in events
                 if e.get("type") in ("item.completed", "item.updated")
                 and (e.get("item") or {}).get("type") == "agent_message"
                 and (e.get("item") or {}).get("text")]
        return texts[-1] if texts else None
    if field == "usage":
        usage = None
        for e in events:
            if e.get("type") == "turn.completed" and e.get("usage"):
                usage = e["usage"]
        return json.dumps(usage) if usage else None
    if field == "errors":
        errs = [json.dumps(e) for e in events if e.get("type") in ("error", "turn.failed")]
        return "\n".join(errs) if errs else None
    if field == "completed":
        return "yes" if any(e.get("type") == "turn.completed" for e in events) else "no"
    if field == "last_event":
        return events[-1].get("type", "unknown") if events else None
    return None


def opencode(events, field):
    if field == "session":
        for e in events:
            sid = find_key(e, {"sessionID", "sessionId", "session_id"})
            if sid:
                return str(sid)
    if field == "final":
        texts = []
        for e in events:
            if e.get("type") == "text":
                t = (e.get("part") or {}).get("text") or e.get("text")
                if t:
                    texts.append(t)
        return "\n".join(texts) if texts else None
    if field == "usage":
        usage = None
        for e in events:
            if e.get("type") in ("step_finish", "step-finish"):
                usage = e.get("part") or e
        return json.dumps(usage) if usage else None
    if field == "errors":
        errs = [json.dumps(e) for e in events
                if e.get("type") == "error" or "error" in e]
        return "\n".join(errs) if errs else None
    if field == "completed":
        has_finish = any(e.get("type") in ("step_finish", "step-finish") for e in events)
        has_text = any(e.get("type") == "text" for e in events)
        return "yes" if (has_finish or has_text) else "no"
    if field == "last_event":
        return events[-1].get("type", "unknown") if events else None
    return None


def gemini(obj, field):
    if obj is None:
        return None
    if field == "session":
        return None  # gemini headless has no resumable session id
    if field == "final":
        return obj.get("response") or None
    if field == "usage":
        stats = obj.get("stats")
        return json.dumps(stats) if stats else None
    if field == "errors":
        err = obj.get("error")
        return json.dumps(err) if err else None
    if field == "completed":
        return "yes" if (obj.get("response") and not obj.get("error")) else "no"
    if field == "last_event":
        return "response" if obj.get("response") else None
    return None


def claude(obj, field):
    """claude -p --output-format json: one result object
    {type:"result", subtype:"success", result, session_id, total_cost_usd, usage}."""
    if obj is None:
        return None
    if field == "session":
        return obj.get("session_id") or None
    if field == "final":
        return obj.get("result") or None
    if field == "usage":
        usage = {}
        for k in ("total_cost_usd", "usage", "num_turns", "modelUsage"):
            if obj.get(k) is not None:
                usage[k] = obj[k]
        return json.dumps(usage) if usage else None
    if field == "errors":
        if obj.get("is_error") or (obj.get("subtype") and obj.get("subtype") != "success"):
            return json.dumps({"subtype": obj.get("subtype"), "result": obj.get("result")})
        return None
    if field == "completed":
        return "yes" if obj.get("subtype") == "success" else "no"
    if field == "last_event":
        return obj.get("type") or None
    return None


def main():
    if len(sys.argv) < 5 or sys.argv[3] != "--format":
        print(__doc__, file=sys.stderr)
        return 2
    path, field, fmt = sys.argv[1], sys.argv[2], sys.argv[4]

    if fmt == "gemini":
        result = gemini(load_object(path), field)
    elif fmt == "claude":
        result = claude(load_object(path), field)
    elif fmt in ("codex", "opencode"):
        events = load_jsonl(path)
        if events is None:
            return 1
        result = codex(events, field) if fmt == "codex" else opencode(events, field)
    else:
        print(f"unknown format: {fmt}", file=sys.stderr)
        return 2

    if result is None or result == "":
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
