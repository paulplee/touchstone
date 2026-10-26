#!/usr/bin/env python3
"""Effort accounting for a pi session transcript (JSONL).

Usage:
  python3 benchmark/session-report.py                 # current $PI_SESSION_FILE
  python3 benchmark/session-report.py path/to.jsonl
  python3 benchmark/session-report.py x.jsonl --since "Create a web-based Tetris"

--since starts the accounting at the first user message containing that text,
so a benchmark run inside a longer session can be measured on its own.
"""
import json, os, sys, datetime
from collections import Counter

def ts(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    since = None
    if "--since" in sys.argv:
        since = sys.argv[sys.argv.index("--since") + 1]
        args = [a for a in args if a != since]
    if "--until" in sys.argv:
        u = sys.argv[sys.argv.index("--until") + 1]
        args = [a for a in args if a != u]
    path = args[0] if args else os.environ.get("PI_SESSION_FILE")
    if not path:
        sys.exit("no session file (pass a path or run inside pi)")

    rows = [json.loads(l) for l in open(path) if l.strip()]
    meta = rows[0]

    window = 262144  # overridden from models.json when the model is listed there
    try:
        models = json.load(open(os.path.expanduser("~/.pi/agent/models.json")))

        def find(o):
            if isinstance(o, dict):
                if o.get("contextWindow"):
                    yield o
                for v in o.values():
                    yield from find(v)
            elif isinstance(o, list):
                for v in o:
                    yield from find(v)

        model = None
        for r in rows:
            if r.get("type") == "model_change":
                model = r.get("modelId")
        for m in find(models):
            if m.get("id") == model:
                window = int(m["contextWindow"])
                break
    except Exception:
        pass
    start = 0
    if since:
        for i, r in enumerate(rows):
            m = r.get("message", {})
            if r.get("type") == "message" and m.get("role") == "user" and since in json.dumps(m):
                start = i
                break
    seg = rows[start:]
    if "--until" in sys.argv:  # stop before a later prompt
        until = sys.argv[sys.argv.index("--until") + 1]
        for i, r in enumerate(seg):
            m = r.get("message", {})
            if i and r.get("type") == "message" and m.get("role") == "user" and until in json.dumps(m):
                seg = seg[:i]
                break

    tok = Counter()
    ctx = []          # per-call input tokens = the size of the context window sent
    calls = Counter()
    models = Counter()
    turns = []
    n_assist = n_tool = 0
    model_ms = 0
    cur = None
    last_event = None
    idle_ms = 0
    cost = Counter()
    for r in seg:
        if r.get("type") != "message":
            continue
        m = r["message"]
        t = ts(r["timestamp"])
        if last_event and m.get("role") == "user":
            idle_ms += (t - last_event).total_seconds() * 1000
        last_event = t
        if m.get("role") == "user":
            txt = " ".join(c.get("text", "") for c in m.get("content", []) if c.get("type") == "text")
            cur = {"t": t, "prompt": txt[:60], "tok": Counter(), "calls": Counter(), "ms": 0, "asst": 0}
            turns.append(cur)
            continue
        if m.get("role") != "assistant":
            n_tool += 1
            continue
        n_assist += 1
        u = m.get("usage", {})
        models[(m.get("provider"), m.get("model"))] += 1
        d = m.get("durationMs", 0) or 0
        model_ms += d
        for k in ("input", "output", "reasoning", "totalTokens"):
            tok[k] += u.get(k, 0) or 0
        if u.get("input"):
            ctx.append(u["input"])
        for k, v in (u.get("cost") or {}).items():
            cost[k] += v or 0
        for c in m.get("content", []):
            if c.get("type") == "toolCall":
                calls[c.get("name")] += 1
        if cur is not None:
            for k in ("input", "output", "reasoning", "totalTokens"):
                cur["tok"][k] += u.get(k, 0) or 0
            for c in m.get("content", []):
                if c.get("type") == "toolCall":
                    cur["calls"][c.get("name")] += 1
            cur["ms"] += d
            cur["asst"] += 1

    t0 = ts(seg[0]["timestamp"])
    t1 = ts(seg[-1]["timestamp"])
    wall = t1 - t0
    print(f"session      {meta.get('id','?')}   cwd {meta.get('cwd','?')}")
    print(f"model        {', '.join(f'{p}/{mo} x{n}' for (p, mo), n in models.items())}")
    print(f"window       {t0:%H:%M:%S} -> {t1:%H:%M:%S}  wall {wall}")
    print(f"assistant    {n_assist} messages, {n_tool} tool results, {len(turns)} user turn(s)")
    print(f"model time   {model_ms/1000:.0f}s ({model_ms/60000:.1f} min)   waiting on human {idle_ms/60000:.1f} min")
    print(f"tokens       in {tok['input']:,}  out {tok['output']:,}  reasoning {tok['reasoning']:,}  total {tok['totalTokens']:,}")
    if ctx:
        print(f"context      first call {ctx[0]:,} -> last {ctx[-1]:,}, peak {max(ctx):,} "
              f"({max(ctx)/window*100:.1f}% of the {window:,}-token window)")
        print(f"             the in/out figures above are CUMULATIVE over {len(ctx)} calls, each of "
              f"which re-sent the whole context;\n             the pi status bar shows only the "
              f"current context ({ctx[-1]:,}), so it reads far smaller.")
    if cost.get("total"):
        print(f"cost         ${cost['total']:.4f}")
    print(f"tools        " + ", ".join(f"{k}={v}" for k, v in calls.most_common()))
    print()
    print(f"{'turn':<3}{'time':<10}{'prompt':<42}{'in':>10}{'out':>8}{'calls':>7}{'model s':>9}")
    for i, tr in enumerate(turns, 1):
        print(f"{i:<3}{tr['t']:%H:%M:%S}  {tr['prompt'][:40]:<42}{tr['tok']['input']:>10,}{tr['tok']['output']:>8,}"
              f"{sum(tr['calls'].values()):>7}{tr['ms']/1000:>9.0f}")

main()
