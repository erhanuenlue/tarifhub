#!/usr/bin/env python3
"""Shipboard v8 — agent-harness trace dashboard for the /ship pipeline. One file, stdlib only.

Everything on the board is clickable: phases, agents, models, commits, ADRs, gate runs,
tasks, alerts — each opens an inspector drawer with the full story behind the number
(GET /detail). The board never asserts a state without being able to show its evidence.

Data sources, in trust order:
  1. explicit /ship emits + agent hooks   (.shipboard/events.jsonl)
  2. the session transcript itself        (main + sidechain subagent files — the event bus;
                                           dispatch prompts, returned reports, gate results,
                                           tool histogram, tool errors; UTC → local)
  3. gh CLI                               (real PR/CI state, cached, fail-silent)
  4. the repo                             (git, ADRs, vault, journal)

Tabs: Overview (command center) · Pipeline (phase cards + feed + PR/CI + gate history)
      · Agents (per-model + timeline + delegation table) · Project (CAS, repo, evidence).

Usage:
  python3 tools/shipboard/shipboard.py            # http://localhost:8787
  python3 tools/shipboard/shipboard.py --demo     # seed demo pipeline events
  python3 tools/shipboard/shipboard.py --reset    # clear pipeline events
Keys: 1–4 switch tabs · Esc closes the inspector.
"""
import json, re, sys, time, pathlib, subprocess, datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

ROOT = pathlib.Path(__file__).resolve().parents[2]
SB = ROOT / ".shipboard"
LOG = SB / "events.jsonl"
SESSION = SB / "session.json"
PORT = 8787

CONTEXT_LIMIT = 1_000_000
SUBMIT_DATE = datetime.date(2026, 7, 5)
BLOCKS = [
    (datetime.date(2026, 6, 10), datetime.date(2026, 6, 14), "Block 0 · Foundation"),
    (datetime.date(2026, 6, 15), datetime.date(2026, 6, 21), "Block 1 · Source + services"),
    (datetime.date(2026, 6, 22), datetime.date(2026, 6, 28), "Block 2 · Console + evidence"),
    (datetime.date(2026, 6, 29), datetime.date(2026, 7, 4),  "Block 3 · Document + Fazit"),
]
PRICES = {"fable": (10.0, 50.0), "opus": (5.0, 25.0), "sonnet": (3.0, 15.0), "haiku": (1.0, 5.0)}
PHASES = [
    ("01", "Plan", "approval gate · Fable 5"),
    ("02", "Implement", "TDD · implementer · Opus 4.8"),
    ("03", "Gates", "ruff + pytest · inline"),
    ("04", "Reviews", "verifier / determinism / security / codex"),
    ("05", "Fix cycle", "orchestrated · Fable 5"),
    ("06", "PR + CI", "gh + Actions · inline"),
    ("07", "Runtime", "E2E + logs · e2e-tester · Sonnet"),
    ("08", "Report", "consolidated · Fable 5"),
    ("09", "Merge", "auto on green · fallback gate: Erhan"),
]
PINS = {"implementer": "Opus 4.8", "e2e-tester": "Sonnet 4.6", "determinism-auditor": "Sonnet 4.6",
        "security-reviewer": "Opus 4.8", "codex-reviewer": "Haiku 4.5", "verifier": "Fable 5"}
REVIEWER_AGENTS = ("verifier", "determinism-auditor", "security-reviewer", "codex-reviewer")
AGENT_TOOLS = ("Task", "Agent")          # subagent tool name differs across Claude Code versions
AGENT_PHASE = {"implementer": "02", "e2e-tester": "07"}

# ---------------- events ----------------

def read_events():
    if not LOG.exists():
        return []
    out = []
    for line in LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out

# ---------------- transcript (incremental, multi-file) ----------------

def _t_blank(tp=None):
    return {"anchor": tp, "files": {}, "models": {}, "turns": 0, "prompts": 0,
            "tools": 0, "ctx": 0, "last_model": "", "mission": "", "todos": [],
            "tasks": {}, "prov": {},
            "delegations": [], "series": [], "t0": "", "t0iso": "",
            "open": {}, "sensed": {}, "sense_log": [], "gates": {}, "gatehist": [],
            "tests": None, "toolhist": {}, "errors": {"n": 0, "last": []},
            "sibs": set(), "rejects": set(), "sibscan": 0.0,
            "fileuse": {}, "first_user": {}, "ithreads": set()}

_T = _t_blank()

def _short(model):
    m = (model or "").lower()
    for k, v in (("fable", "Fable 5"), ("opus", "Opus 4.8"), ("sonnet", "Sonnet 4.6"), ("haiku", "Haiku 4.5")):
        if k in m:
            return v
    return model or "?"

def _price(model):
    m = (model or "").lower()
    for key, p in PRICES.items():
        if key in m:
            return p
    return (0.0, 0.0)

def _local_hms(iso):
    """Transcript timestamps are UTC ISO — convert to LOCAL wall-clock HH:MM:SS."""
    if not iso or len(iso) < 19:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone()
        return dt.strftime("%H:%M:%S")
    except Exception:
        return iso[11:19]

def _ts(e):
    return _local_hms(e.get("timestamp") or "")

def _tsec(hms):
    try:
        h, m, s = (hms or "").split(":")
        return int(h) * 3600 + int(m) * 60 + int(s)
    except Exception:
        return None

def _dursec(a, b):
    x, y = _tsec(a), _tsec(b)
    if x is None or y is None:
        return None
    d = y - x
    if d < 0:
        d += 86400
    return d if 0 <= d < 86400 else None

def _cost_of(models):
    c = 0.0
    for model, m in models.items():
        pi, po = _price(model)
        c += (m["in"] * pi + m["cr"] * pi * 0.1 + m["cw"] * pi * 1.25 + m["out"] * po) / 1e6
    return c

def _fu_cost(fu):
    pi, po = _price(fu.get("model", ""))
    return (fu["in"] * pi + fu["cr"] * pi * 0.1 + fu["cw"] * pi * 1.25 + fu["out"] * po) / 1e6

def _sense(t, phase, status, detail, ts):
    """Latest evidence wins; a terminal state is only re-opened by NEWER running evidence (new cycle)."""
    cur = t["sensed"].get(phase)
    if cur and status == "running" and cur["status"] in ("pass", "fail") and not (ts and ts > cur["ts"]):
        return
    t["sensed"][phase] = {"status": status, "detail": (detail or "")[:80], "ts": ts}
    t["sense_log"].append({"ph": phase, "st": status, "d": (detail or "")[:80], "ts": ts})
    t["sense_log"] = t["sense_log"][-80:]

def _is_meta_user(e, text):
    if e.get("isMeta"):
        return True
    s = (text or "").lstrip()
    return s.startswith("<") or s.startswith("Caveat:")

def _cmdsum(cmd):
    """'cd /long/path && (cd services/serving && uv run pytest -q)' → 'serving · uv run pytest -q'"""
    c = " ".join((cmd or "").split())
    svc = ""
    for m in re.findall(r"cd\s+([^\s&;()]+)", c):
        b = m.rstrip("/").split("/")[-1]
        if b and b not in (".", ".."):
            svc = b
    while True:
        m = re.match(r"^[(\s]*cd\s+[^&;]+?(?:&&|;)\s*", c)
        if not m:
            break
        c = c[m.end():]
    c = c.strip("() ")
    for key in ("uv run pytest", "uv run ruff", "pytest", "ruff", "npm run", "npm test",
                "gh pr create", "gh pr merge", "gh run", "git push", "docker compose", "mkdocs"):
        i = c.find(key)
        if i > 0:
            c = c[i:]
            break
    return ((svc + " · ") if svc and svc not in c[:40] else "") + c[:72]

def _result_text(x):
    c = x.get("content")
    if isinstance(c, str):
        return c
    out = []
    if isinstance(c, list):
        for i in c:
            if isinstance(i, dict) and i.get("type") == "text":
                out.append(i.get("text", ""))
            elif isinstance(i, str):
                out.append(i)
    return "\n".join(out)

def _agent_counts(t, agents):
    if isinstance(agents, str):
        agents = (agents,)
    tot = sum(1 for x in t["delegations"] if x["agent"] in agents)
    done = sum(1 for x in t["delegations"] if x["agent"] in agents and x["done"])
    return done, tot

def _parse_file(t, path, main):
    """Incrementally parse one transcript file. main=True → also ctx/series/mission/tasks/delegations/sensing."""
    try:
        size = path.stat().st_size
    except Exception:
        return
    key = str(path)
    off = t["files"].get(key, 0)
    if size < off:          # rotated/shrunk → cannot safely re-add; skip residual
        t["files"][key] = size
        return
    if size == off:
        return
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            f.seek(off)
            for line in f:
                off += len(line.encode("utf-8", "replace"))
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                msg = e.get("message") or {}
                ets = _ts(e)
                side_entry = main and bool(e.get("isSidechain"))
                if side_entry:
                    t["ithreads"].add(e.get("sessionId") or e.get("agentId") or "x")
                if main and not t["t0"] and ets:
                    t["t0"] = ets
                    t["t0iso"] = e.get("timestamp") or ""
                if e.get("type") == "assistant":
                    u = msg.get("usage") or {}
                    model = msg.get("model", "")
                    if u:
                        mt = t["models"].setdefault(model or t["last_model"], {"in": 0, "out": 0, "cr": 0, "cw": 0})
                        mt["in"] += u.get("input_tokens", 0) or 0
                        mt["out"] += u.get("output_tokens", 0) or 0
                        mt["cr"] += u.get("cache_read_input_tokens", 0) or 0
                        mt["cw"] += u.get("cache_creation_input_tokens", 0) or 0
                        if main and not side_entry:
                            t["turns"] += 1
                            t["last_model"] = model or t["last_model"]
                            t["ctx"] = ((u.get("input_tokens", 0) or 0)
                                        + (u.get("cache_read_input_tokens", 0) or 0)
                                        + (u.get("cache_creation_input_tokens", 0) or 0))
                            t["series"].append({"i": len(t["series"]) + 1, "ts": ets, "ctx": t["ctx"],
                                                "cost": round(_cost_of(t["models"]), 4),
                                                "out": sum(m["out"] for m in t["models"].values())})
                            t["series"] = t["series"][-400:]
                        elif not main:
                            fu = t["fileuse"].setdefault(key, {"model": "", "in": 0, "out": 0, "cr": 0,
                                                               "cw": 0, "t0": ets, "t1": ets})
                            if model:
                                fu["model"] = model
                            fu["in"] += u.get("input_tokens", 0) or 0
                            fu["out"] += u.get("output_tokens", 0) or 0
                            fu["cr"] += u.get("cache_read_input_tokens", 0) or 0
                            fu["cw"] += u.get("cache_creation_input_tokens", 0) or 0
                            fu["t1"] = ets or fu["t1"]
                    for c in (msg.get("content") or []):
                        if not (isinstance(c, dict) and c.get("type") == "tool_use"):
                            continue
                        t["tools"] += 1
                        if not main or side_entry:
                            continue
                        name = c.get("name", "")
                        t["toolhist"][name] = t["toolhist"].get(name, 0) + 1
                        inp = c.get("input") or {}
                        if name == "TodoWrite" and isinstance(inp.get("todos"), list):
                            t["todos"] = [{"content": (x.get("content") or "")[:100],
                                           "status": x.get("status", "pending")}
                                          for x in inp["todos"]][:40]
                        elif name == "TaskCreate":
                            subj = (inp.get("subject") or "")[:100]
                            if subj and c.get("id"):
                                t["prov"][c["id"]] = {"content": subj, "status": "pending"}
                        elif name == "TaskUpdate":
                            tid = str(inp.get("taskId") or "")
                            if tid:
                                row = t["tasks"].setdefault(tid, {"content": f"task #{tid}", "status": "pending"})
                                if inp.get("subject"):
                                    row["content"] = inp["subject"][:100]
                                st = inp.get("status")
                                if st == "deleted":
                                    t["tasks"].pop(tid, None)
                                elif st:
                                    row["status"] = st
                        elif name in AGENT_TOOLS:
                            agent = inp.get("subagent_type", "subagent")
                            desc = (inp.get("description") or "")[:70]
                            d = {"agent": agent, "desc": desc, "ts": ets, "done": False, "live": True,
                                 "done_ts": "", "prompt": (inp.get("prompt") or "")[:1200],
                                 "report": "", "file": ""}
                            t["delegations"].append(d)
                            t["delegations"] = t["delegations"][-40:]
                            if c.get("id"):
                                t["open"][c["id"]] = d
                            ph = AGENT_PHASE.get(agent)
                            if ph:
                                _sense(t, ph, "running", desc, ets)
                            elif agent.lower() == "plan":
                                _sense(t, "01", "running", desc or "planning", ets)
                            elif agent in REVIEWER_AGENTS:
                                _sense(t, "04", "running", agent, ets)
                        elif name == "Bash":
                            cmd = (inp.get("command") or "")[:400]
                            if "pytest" in cmd or ("ruff" in cmd and "uv" in cmd) or cmd.startswith("ruff"):
                                _sense(t, "03", "running", _cmdsum(cmd), ets)
                                if c.get("id"):
                                    t["gates"][c["id"]] = {"kind": "pytest" if "pytest" in cmd else "ruff",
                                                           "ts": ets, "cmd": _cmdsum(cmd)}
                            elif "gh pr create" in cmd:
                                _sense(t, "06", "running", "PR created", ets)
                            elif "gh pr merge" in cmd:
                                _sense(t, "09", "pass", "merged", ets)
                                _sense(t, "06", "pass", "PR merged", ets)
                            elif "git push" in cmd:
                                _sense(t, "06", "running", "pushed", ets)
                elif e.get("type") == "user":
                    c = msg.get("content")
                    text = None
                    if isinstance(c, list):
                        for x in c:
                            if not isinstance(x, dict):
                                continue
                            if x.get("type") == "tool_result" and main and not side_entry:
                                if x.get("is_error"):
                                    t["errors"]["n"] += 1
                                    t["errors"]["last"].append({"ts": ets, "txt": _result_text(x)[:220]})
                                    t["errors"]["last"] = t["errors"]["last"][-5:]
                                xid = x.get("tool_use_id")
                                if xid in t["open"]:
                                    d = t["open"].pop(xid)
                                    d["done"] = True
                                    d["live"] = False
                                    d["done_ts"] = ets
                                    d["report"] = _result_text(x)[:2200]
                                    ag = d["agent"]
                                    if ag in AGENT_PHASE and not any(
                                            v["agent"] == ag for v in t["open"].values()):
                                        dn, tot = _agent_counts(t, ag)
                                        lbl = {"02": f"{dn}/{tot} implementers returned",
                                               "07": "runtime verified"}[AGENT_PHASE[ag]]
                                        _sense(t, AGENT_PHASE[ag], "pass", lbl, ets)
                                    if ag in REVIEWER_AGENTS and not any(
                                            v["agent"] in REVIEWER_AGENTS for v in t["open"].values()):
                                        dn, tot = _agent_counts(t, REVIEWER_AGENTS)
                                        _sense(t, "04", "pass", f"{dn}/{tot} reviewers returned", ets)
                                    if ag.lower() == "plan":
                                        _sense(t, "01", "running", "plan drafted · awaiting Erhan", ets)
                                elif xid in t["prov"]:
                                    row = t["prov"].pop(xid)
                                    m = re.search(r"#(\d+)", _result_text(x)[:120])
                                    t["tasks"][m.group(1) if m else f"p{len(t['tasks'])}"] = row
                                elif xid in t["gates"]:
                                    g = t["gates"].pop(xid)
                                    txt = _result_text(x)[:4000]
                                    rec = {"kind": g["kind"], "ts": ets, "cmd": g.get("cmd", ""),
                                           "passed": None, "failed": None, "ok": True}
                                    if g["kind"] == "pytest":
                                        mp = re.search(r"(\d+) passed", txt)
                                        mf = re.search(r"(\d+) failed", txt)
                                        me = re.search(r"(\d+) error", txt)
                                        np_, nf = int(mp.group(1)) if mp else 0, int(mf.group(1)) if mf else 0
                                        nf += int(me.group(1)) if me else 0
                                        if mp or mf or me:
                                            t["tests"] = {"passed": np_, "failed": nf, "ts": ets}
                                            rec.update({"passed": np_, "failed": nf, "ok": nf == 0})
                                            if nf:
                                                _sense(t, "03", "fail", f"{nf} failed · {np_} passed", ets)
                                            else:
                                                _sense(t, "03", "pass", f"{np_} passed", ets)
                                            t["gatehist"].append(rec)
                                        elif re.search(r"\bFAIL(ED)?\b", txt):
                                            rec.update({"ok": False})
                                            _sense(t, "03", "fail", "gates FAIL — see terminal", ets)
                                            t["gatehist"].append(rec)
                                        elif re.search(r"\bPASS(ED)?\b", txt):
                                            rec.update({"ok": True})
                                            _sense(t, "03", "pass", "gates PASS (output suppressed)", ets)
                                            t["gatehist"].append(rec)
                                    else:
                                        if "All checks passed" in txt:
                                            _sense(t, "03", "running", "ruff clean", ets)
                                            t["gatehist"].append(rec)
                                        else:
                                            mr = re.search(r"Found (\d+) error", txt)
                                            if mr and int(mr.group(1)) > 0:
                                                rec.update({"failed": int(mr.group(1)), "ok": False})
                                                _sense(t, "03", "fail", f"ruff: {mr.group(1)} errors", ets)
                                                t["gatehist"].append(rec)
                                    t["gatehist"] = t["gatehist"][-25:]
                            elif x.get("type") == "text" and text is None:
                                text = x.get("text", "")
                    elif isinstance(c, str):
                        text = c
                    if text is not None:
                        if main and not side_entry and not _is_meta_user(e, text):
                            t["prompts"] += 1
                            first = text.strip().splitlines()[0] if text.strip() else ""
                            if first:
                                t["mission"] = first[:160].rstrip("—- ")
                        elif not main and key not in t["first_user"] and text.strip():
                            t["first_user"][key] = text[:300]
    except Exception:
        pass
    t["files"][key] = off

def _scan_sidechains(t, anchor):
    """Find subagent transcripts anywhere under the project dir: content-sniffed, session-window-gated."""
    now = time.time()
    if now - t["sibscan"] < 20:
        return
    t["sibscan"] = now
    horizon = now - 14 * 3600
    n = 0
    try:
        for p in anchor.parent.rglob("*.jsonl"):
            n += 1
            if n > 500:
                break
            key = str(p)
            if p == anchor or key in t["sibs"] or key in t["rejects"]:
                continue
            try:
                if p.stat().st_mtime < horizon:
                    t["rejects"].add(key)
                    continue
                with open(p, encoding="utf-8", errors="replace") as f:
                    head = f.readline(6000)
                e = json.loads(head)
                if not e.get("isSidechain"):
                    t["rejects"].add(key)
                    continue
                ts0 = e.get("timestamp") or ""
                if t["t0iso"] and ts0 and ts0 < t["t0iso"]:
                    t["rejects"].add(key)
                    continue
                t["sibs"].add(key)
            except Exception:
                t["rejects"].add(key)
    except Exception:
        pass

def _attribute(t):
    """Match sidechain files to delegations: prompt-prefix first, then time-window fallback."""
    used = {d.get("file") for d in t["delegations"] if d.get("file")}
    for key, ftxt in t["first_user"].items():
        if key in used or key not in t["fileuse"]:
            continue
        for d in t["delegations"]:
            if d.get("file"):
                continue
            pp = (d.get("prompt") or "")[:80]
            if (pp and (ftxt.startswith(pp) or pp in ftxt[:400])) or (d["desc"] and d["desc"] in ftxt[:240]):
                d["file"] = key
                used.add(key)
                break
    free = [k for k in t["fileuse"] if k not in used]
    for d in t["delegations"]:
        if d.get("file") or not d["ts"]:
            continue
        best, bestdt = None, 99999
        for k in free:
            dt = _dursec(d["ts"], t["fileuse"][k].get("t0", ""))
            if dt is None:
                continue
            if dt > 86000:  # wrapped negative → file started slightly before dispatch
                if 86400 - dt <= 30:
                    dt = 0
                else:
                    continue
            if dt <= 240 and dt < bestdt:
                best, bestdt = k, dt
        if best:
            d["file"] = best
            free.remove(best)
            used.add(best)

def _enrich(d, t):
    r = {"agent": d["agent"], "desc": d["desc"], "ts": d["ts"], "done": d["done"],
         "done_ts": d.get("done_ts", ""), "live": d.get("live", False),
         "model": PINS.get(d["agent"], ""),
         "dur_s": _dursec(d["ts"], d.get("done_ts", "")) if d["done"] else None,
         "cost": None, "tin": None, "tout": None, "has_report": bool(d.get("report"))}
    fu = t["fileuse"].get(d.get("file") or "")
    if fu:
        if fu.get("model"):
            r["model"] = _short(fu["model"])
        r["cost"] = round(_fu_cost(fu), 2)
        r["tin"] = fu["in"] + fu["cr"] + fu["cw"]
        r["tout"] = fu["out"]
        if d["done"] and r["dur_s"] is None:
            r["dur_s"] = _dursec(fu.get("t0", ""), fu.get("t1", ""))
    return r

def parse_transcript():
    sess = {}
    try:
        sess = json.loads(SESSION.read_text())
    except Exception:
        pass
    tp = sess.get("transcript_path")
    t = _T
    idle = 0
    if tp and pathlib.Path(tp).exists():
        anchor = pathlib.Path(tp)
        if t["anchor"] != tp:
            t.clear()
            t.update(_t_blank(tp))
        main_p = pathlib.Path(t.get("mainfile") or tp)
        _parse_file(t, main_p, main=True)
        # tracker heal: a short empty session can steal session.json (last-writer-wins).
        # If the tracked transcript has no prompts and its session is over, switch to the
        # most substantial recently-active MAIN transcript in the same project dir.
        if not t.get("healed") and t["prompts"] == 0 and sess.get("status") == "ended":
            best = None
            try:
                for p in anchor.parent.glob("*.jsonl"):
                    st = p.stat()
                    if p == main_p or st.st_size < 20000 or time.time() - st.st_mtime > 86400:
                        continue
                    with open(p, encoding="utf-8", errors="replace") as f:
                        head = f.readline(4000)
                    if '"isSidechain": true' in head or '"isSidechain":true' in head:
                        continue
                    if best is None or st.st_mtime > best.stat().st_mtime:
                        best = p
            except Exception:
                pass
            t["healed"] = True
            if best:
                healed_tp = t["anchor"]
                t.clear()
                t.update(_t_blank(healed_tp))
                t["mainfile"] = str(best)
                t["healed"] = True
                main_p = best
                _parse_file(t, main_p, main=True)
        _scan_sidechains(t, main_p)
        for key in sorted(t["sibs"]):
            _parse_file(t, pathlib.Path(key), main=False)
        try:
            idle = max(0, int(time.time() - main_p.stat().st_mtime))
        except Exception:
            idle = 0
    _attribute(t)
    rows = [_enrich(d, t) for d in reversed(t["delegations"])]
    side_cost = sum(_fu_cost(fu) for fu in t["fileuse"].values())
    tin = sum(m["in"] for m in t["models"].values())
    tout = sum(m["out"] for m in t["models"].values())
    tcr = sum(m["cr"] for m in t["models"].values())
    tcw = sum(m["cw"] for m in t["models"].values())
    denom = tin + tcr + tcw
    per_model = []
    for model, m in sorted(t["models"].items(), key=lambda kv: -_cost_of({kv[0]: kv[1]})):
        pi, po = _price(model)
        per_model.append({"model": model, "short": _short(model), "in": m["in"], "out": m["out"],
                          "cr": m["cr"], "cw": m["cw"],
                          "cost": round((m["in"]*pi + m["cr"]*pi*0.1 + m["cw"]*pi*1.25 + m["out"]*po)/1e6, 2)})
    cache_saved = round(sum(m["cr"] * _price(mod)[0] * 0.9 for mod, m in t["models"].items()) / 1e6, 2)
    total = round(_cost_of(t["models"]), 2)
    sess_secs = _dursec(t["t0"], time.strftime("%H:%M:%S")) if t["t0"] else None
    todos = t["todos"] if t["todos"] else [
        {"content": v["content"], "status": v["status"]}
        for k, v in sorted(t["tasks"].items(), key=lambda kv: (len(kv[0]), kv[0]))][:40]
    th = sorted(t["toolhist"].items(), key=lambda kv: -kv[1])[:8]
    side = len(t["sibs"]) + len(t["ithreads"])
    return {
        "session": {"id": (sess.get("session_id") or "")[:8],
                    "status": sess.get("status", "none"),
                    "started": sess.get("started", ""),
                    "last_activity": sess.get("last_activity", ""),
                    "compactions": sess.get("compactions", 0)},
        "t0": t["t0"], "idle_sec": idle, "sess_secs": sess_secs,
        "healed": bool(t.get("healed") and t.get("mainfile")),
        "ctx": t["ctx"], "ctx_limit": CONTEXT_LIMIT,
        "ctx_pct": round(100.0 * t["ctx"] / CONTEXT_LIMIT, 1) if t["ctx"] else 0.0,
        "tokens": {"in": tin, "out": tout, "cache_read": tcr, "cache_write": tcw},
        "cache_hit_pct": round(100.0 * tcr / denom, 1) if denom else 0.0,
        "cache_saved": cache_saved,
        "turns": t["turns"], "prompts": t["prompts"], "tools": t["tools"],
        "cost_usd": total, "cost_side": round(side_cost, 2),
        "cost_main": round(max(0.0, total - side_cost), 2), "tracked": bool(tp),
        "mission": t["mission"], "todos": todos,
        "delegations": rows, "per_model": per_model,
        "series": t["series"], "side": side,
        "side_matched": sum(1 for d in t["delegations"] if d.get("file")),
        "tests": t["tests"], "gatehist": t["gatehist"][::-1][:8],
        "toolhist": th, "errors": {"n": t["errors"]["n"], "last": t["errors"]["last"][::-1]},
        "live": [{"agent": v["agent"], "desc": v["desc"], "ts": v["ts"]} for v in t["open"].values()],
        "sensed": t["sensed"],
    }

# ---------------- vault wikilink graph (cached 10s) ----------------

_VG = {"ts": 0.0, "data": None}

def vault_graph():
    now = time.time()
    if _VG["data"] and now - _VG["ts"] < 10:
        return _VG["data"]
    files = []
    vd = ROOT / "vault"
    if vd.is_dir():
        for p in sorted(vd.glob("*.md")):
            files.append((p, "hub" if p.stem == "00-index" else "reflect"))
        files += [(p, "journal") for p in sorted((vd / "daily").glob("*.md"))[-14:]]
    for p in sorted((ROOT / "docs" / "adr").glob("[0-9]*.md")):
        files.append((p, "adr"))
    for p in sorted((ROOT / "docs" / "arc42").glob("[0-9]*.md")):
        files.append((p, "arc"))
    if (ROOT / "LEARNINGS.md").exists():
        files.append((ROOT / "LEARNINGS.md", "reflect"))
    nodes, texts = {}, {}
    for p, t in files:
        label = p.stem
        if t == "adr":
            try:
                label = re.sub(r"^[^A-Za-z0-9]+", "",
                               p.read_text(errors="replace").splitlines()[0])[:40]
            except Exception:
                pass
        nodes[p.stem.lower()] = {"id": p.stem, "label": label, "t": t,
                                 "f": p.name if t == "adr" else ""}
        try:
            texts[p.stem.lower()] = p.read_text(errors="replace")[:200000]
        except Exception:
            texts[p.stem.lower()] = ""
    edges = set()
    for src, txt in texts.items():
        targets = [m.strip().lower() for m in re.findall(r"\[\[([^\]|#]+)", txt)]
        # markdown relative links count too — arc42 chapters and the ADR register
        # cross-reference each other this way (that's the real structure)
        targets += [pathlib.Path(m).stem.lower()
                    for m in re.findall(r"\]\(([^)#?\s]+\.md)\)", txt)]
        for tgt in targets:
            if tgt in nodes and tgt != src:
                edges.add(tuple(sorted((nodes[src]["id"], nodes[tgt]["id"]))))
    data = {"nodes": list(nodes.values()), "edges": [list(e) for e in edges],
            "updated": time.strftime("%H:%M:%S")}
    _VG.update(ts=now, data=data)
    return data

# ---------------- gh (PR + CI, cached 45s, fail-silent) ----------------

_GH = {"ts": 0.0, "data": None}

def gh_info():
    now = time.time()
    if now - _GH["ts"] < 45:
        return _GH["data"]
    _GH["ts"] = now
    data = {"prs": [], "runs": []}
    try:
        r = subprocess.run(["gh", "pr", "list", "--json", "number,title,headRefName,statusCheckRollup",
                            "--limit", "6"], cwd=ROOT, capture_output=True, text=True, timeout=4)
        if r.returncode == 0 and r.stdout.strip():
            for pr in json.loads(r.stdout):
                ok = fail = pend = 0
                for c in pr.get("statusCheckRollup") or []:
                    v = (c.get("conclusion") or c.get("state") or "").upper()
                    if v == "SUCCESS":
                        ok += 1
                    elif v in ("FAILURE", "ERROR", "TIMED_OUT", "STARTUP_FAILURE"):
                        fail += 1
                    else:
                        pend += 1
                data["prs"].append({"n": pr.get("number"), "t": (pr.get("title") or "")[:64],
                                    "br": pr.get("headRefName", ""), "ok": ok, "fail": fail, "pend": pend})
    except Exception:
        pass
    try:
        r = subprocess.run(["gh", "run", "list", "--json", "workflowName,status,conclusion,headBranch,createdAt",
                            "--limit", "5"], cwd=ROOT, capture_output=True, text=True, timeout=4)
        if r.returncode == 0 and r.stdout.strip():
            for run in json.loads(r.stdout):
                data["runs"].append({"wf": (run.get("workflowName") or "")[:22],
                                     "st": (run.get("conclusion") or run.get("status") or "")[:12],
                                     "br": (run.get("headBranch") or "")[:26],
                                     "at": (run.get("createdAt") or "")[11:16]})
    except Exception:
        pass
    if not data["prs"] and not data["runs"]:
        data = None
    _GH["data"] = data
    return data

# ---------------- project (cached 5s) ----------------

_P = {"ts": 0.0, "data": None}

def _git(*args):
    try:
        r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=3)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""

def _count_lines(path, pattern):
    try:
        return len(re.findall(pattern, path.read_text(encoding="utf-8", errors="replace"), re.M))
    except Exception:
        return 0

def _service_shape():
    out = []
    for base, exts in (("services", (".py",)), ("apps", (".ts", ".tsx", ".js", ".jsx"))):
        root = ROOT / base
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            src = tests = 0
            for f in d.rglob("*"):
                if "node_modules" in f.parts or ".venv" in f.parts:
                    continue
                if f.suffix in exts:
                    if f.name.startswith("test_") or ".test." in f.name or ".spec." in f.name:
                        tests += 1
                    else:
                        src += 1
            out.append({"n": f"{base}/{d.name}", "src": src, "tests": tests})
    return out[:10]

def project():
    now = time.time()
    if _P["data"] and now - _P["ts"] < 5:
        return _P["data"]
    today = datetime.date.today()
    commits = [l for l in _git("log", "-8", "--format=%h · %s · %cr").splitlines() if l]
    adr_files = sorted((ROOT / "docs" / "adr").glob("[0-9]*.md"))
    adrs = []
    for f in adr_files:
        title, status = f.stem, ""
        try:
            head = f.read_text(encoding="utf-8", errors="replace")[:1500]
            title = head.splitlines()[0].lstrip("# ").strip()
            m = re.search(r"(?im)^\**\s*status\s*[:*]*\s*([a-z]+)", head)
            if m:
                status = m.group(1).lower()
            elif re.search(r"(?i)superseded", head):
                status = "superseded"
        except Exception:
            pass
        adrs.append({"t": title[:90], "s": status, "f": f.name})
    daily = sorted((ROOT / "vault" / "daily").glob("*.md"))
    today_file = ROOT / "vault" / "daily" / f"{today.isoformat()}.md"
    preview = []
    if today_file.exists():
        try:
            preview = [l for l in today_file.read_text(encoding="utf-8").splitlines() if l.strip()][:26]
        except Exception:
            pass
    blocks = []
    for start, end, label in BLOCKS:
        statee = "done" if today > end else ("now" if start <= today <= end else "next")
        pct = 0
        if statee == "now":
            pct = round(100 * ((today - start).days + 1) / ((end - start).days + 1))
        blocks.append({"label": label, "state": statee, "pct": pct,
                       "range": f"{start.strftime('%d.%m')}–{end.strftime('%d.%m')}"})
    flags = {
        "compose": (ROOT / "deploy" / "docker-compose.yml").exists(),
        "helm": any((ROOT / "deploy").rglob("Chart.yaml")) if (ROOT / "deploy").is_dir() else False,
        "boundary": any(ROOT.rglob("test_*boundary*.py")),
        "ci": (ROOT / ".github" / "workflows" / "ci.yml").exists(),
        "docs": (ROOT / "docs" / "mkdocs.yml").exists(),
    }
    data = {
        "git": {"branch": _git("branch", "--show-current") or "—",
                "dirty": len([l for l in _git("status", "--porcelain").splitlines() if l.strip()]),
                "ahead": _git("rev-list", "--count", "origin/main..HEAD") or "0",
                "commits": commits or ["no commits yet"]},
        "adrs": {"count": len(adr_files), "list": adrs[::-1][:14]},
        "journal": {"entries": len(daily), "today": today_file.exists(), "preview": preview},
        "vault": {"fazit": _count_lines(ROOT / "vault" / "fazit-notes.md", r"^- "),
                  "learnings": _count_lines(ROOT / "LEARNINGS.md", r"^(##|- )")},
        "services": _service_shape(),
        "flags": flags,
        "cas": {"days_left": (SUBMIT_DATE - today).days, "blocks": blocks,
                "block": next((b["label"] for b in blocks if b["state"] == "now"), "post-CAS")},
    }
    _P.update({"ts": now, "data": data})
    return data

# ---------------- alerts + phase computation ----------------

def alerts(u, p, phases, ghd):
    out = []
    if not u["tracked"]:
        out.append({"lvl": "warn", "msg": "session not tracked — start a Claude session with hooks armed"})
    if u["ctx_pct"] > 80:
        out.append({"lvl": "bad", "msg": f"context at {u['ctx_pct']}% — compaction imminent; consider /clear after shipping"})
    elif u["ctx_pct"] > 60:
        out.append({"lvl": "warn", "msg": f"context at {u['ctx_pct']}%"})
    if u["session"]["compactions"]:
        out.append({"lvl": "warn", "msg": f"{u['session']['compactions']} compaction(s) this session — early context lost"})
    if u["tests"] and u["tests"]["failed"]:
        out.append({"lvl": "bad", "msg": f"{u['tests']['failed']} test(s) failing as of {u['tests']['ts']}"})
    if u["errors"]["n"] >= 5:
        out.append({"lvl": "warn", "msg": f"{u['errors']['n']} tool errors this session — inspect the last ones (Overview → errors)"})
    if ghd:
        for pr in ghd["prs"]:
            if pr["fail"]:
                out.append({"lvl": "bad", "msg": f"CI red on PR #{pr['n']} ({pr['br']})"})
    for d in u["delegations"]:
        if d["live"]:
            el = _dursec(d["ts"], time.strftime("%H:%M:%S"))
            if el and el > 1800:
                out.append({"lvl": "warn", "msg": f"{d['agent']} running {el//60}m — long; check it"})
    running = any(v["status"] == "running" for v in phases.values())
    if running and u["idle_sec"] > 900:
        out.append({"lvl": "warn", "msg": f"pipeline open but session idle {u['idle_sec']//60}m"})
    if not p["journal"]["today"]:
        out.append({"lvl": "bad", "msg": "no journal entry today — criterion 15 evidence is contemporaneous-only"})
    if p["git"]["dirty"] > 40:
        out.append({"lvl": "warn", "msg": f"{p['git']['dirty']} uncommitted changes — ship or commit soon"})
    dl = p["cas"]["days_left"]
    if 0 <= dl <= 7:
        out.append({"lvl": "bad", "msg": f"{dl} days to submission"})
    elif 8 <= dl <= 14:
        out.append({"lvl": "warn", "msg": f"{dl} days to submission"})
    return out[:8]

def _phid(v):
    """Normalize phase ids: '01', 'phase01', '1', 'phase 1' → '01'."""
    m = re.search(r"(\d{1,2})", str(v or ""))
    return m.group(1).zfill(2) if m else ""

def compute_phases(ev, u, p, ghd):
    phases = {x[0]: {"status": "pending", "detail": "", "ts": "", "src": ""} for x in PHASES}
    explicit = set()
    for e in ev:
        ph = _phid(e.get("phase"))
        if e.get("kind") == "phase" and ph in phases:
            phases[ph] = {"status": e.get("status", "?"), "detail": e.get("detail", ""),
                          "ts": (e.get("ts", "") or "")[11:19] or e.get("ts", ""), "src": "emit"}
            explicit.add(ph)
    for ph, st in (u.get("sensed") or {}).items():
        if ph in phases and ph not in explicit:
            phases[ph] = {"status": st["status"], "detail": st["detail"], "ts": st["ts"], "src": "sensed"}
    # gh refines phase 06 ONLY once this run has its own 06 evidence (sensed PR/push) —
    # an open PR on the branch is repo-level truth, not proof this run reached phase 06
    if ghd and "06" not in explicit and (u.get("sensed") or {}).get("06"):
        pr = next((x for x in ghd["prs"] if x["br"] == p["git"]["branch"]), None)
        if pr:
            tag = f"PR #{pr['n']} · {pr['ok']}✓"
            if pr["fail"]:
                phases["06"] = {"status": "fail", "detail": f"CI red · {tag} {pr['fail']}✗", "ts": phases["06"]["ts"], "src": "gh"}
            elif pr["pend"]:
                phases["06"] = {"status": "running", "detail": f"CI running · {tag} {pr['pend']}◌", "ts": phases["06"]["ts"], "src": "gh"}
            elif pr["ok"]:
                phases["06"] = {"status": "pass", "detail": f"CI green · {tag}", "ts": phases["06"]["ts"], "src": "gh"}
    # ordered-pipeline inference: WORK-phase evidence implies the plan gate was passed —
    # never while a Plan agent is live, and never from repo-level (gh) signals alone
    plan_live = any((d.get("agent") or "").lower() == "plan" for d in (u.get("live") or []))
    p1_upgradable = (phases["01"]["status"] == "pending"
                     or (phases["01"]["src"] == "sensed" and phases["01"]["status"] == "running"))
    if p1_upgradable and not plan_live and any(
            phases[k]["status"] != "pending" for k in ("02", "03", "04", "07")):
        phases["01"] = {"status": "pass", "ts": "",
                        "detail": "implied — implementation ran, and the contract forbids it before plan approval",
                        "src": "implied"}
    if phases["08"]["status"] == "pending" and phases["09"]["status"] == "pass":
        phases["08"] = {"status": "pass", "ts": "",
                        "detail": "implied — merge confirmed, and the report precedes the merge gate",
                        "src": "implied"}
    # downstream completion supersedes a stale upstream 'running' — a session that
    # skips a completion emit must not freeze the rail forever
    order = [x[0] for x in PHASES]
    for i, k in enumerate(order):
        if phases[k]["status"] != "running" or not phases[k]["ts"]:
            continue
        for j in order[i + 1:]:
            pj = phases[j]
            if pj["status"] == "pass" and pj["ts"] and pj["ts"] > phases[k]["ts"]:
                phases[k] = {"status": "pass", "ts": pj["ts"],
                             "detail": f"implied — phase {j} passed after this started",
                             "src": "implied"}
                break
    return phases, explicit

def state():
    ev = read_events()
    agents = [e for e in ev if e.get("kind") == "agent"]
    active = {}
    for a in agents:
        if a.get("status") == "active":
            active[a.get("agent")] = a
        elif a.get("status") == "done":
            active.pop(a.get("agent"), None)
    u = parse_transcript()
    p = project()
    ghd = gh_info()
    phases, _ = compute_phases(ev, u, p, ghd)
    merged = {a.get("agent"): {"agent": a.get("agent"), "model": a.get("model", ""),
                               "desc": "", "ts": (a.get("ts", "") or "")[11:19]} for a in active.values()}
    for d in u.get("live") or []:
        merged[d["agent"]] = {"agent": d["agent"], "model": PINS.get(d["agent"], ""),
                              "desc": d.get("desc", ""), "ts": d.get("ts", "")}
    feed, seen = [], set()
    for e in ev:
        ts = e.get("ts", "") or ""
        hms = ts[11:19] if len(ts) >= 19 else ts
        seen.add((e.get("agent") or e.get("phase") or "", e.get("status", ""), hms[:5]))
        feed.append({"ts": hms, "kind": e.get("kind", "?"), "status": e.get("status", ""),
                     "agent": e.get("agent", ""), "model": e.get("model", ""),
                     "phase": _phid(e.get("phase")), "detail": e.get("detail", ""), "src": "hook"})
    for d in u["delegations"]:
        for st, tt in (("active", d["ts"]), ("done", d.get("done_ts") if d["done"] else "")):
            if not tt:
                continue
            if (d["agent"], st, tt[:5]) in seen:
                continue
            feed.append({"ts": tt, "kind": "agent", "status": st, "agent": d["agent"],
                         "model": d.get("model", ""), "phase": "", "detail": d["desc"], "src": "transcript"})
    feed.sort(key=lambda r: r["ts"], reverse=True)
    return {"phases": phases, "active": list(merged.values()),
            "updated": time.strftime("%H:%M:%S"), "events": len(ev),
            "event_tail": ev[-40:][::-1], "feed": feed[:40],
            "usage": u, "project": p, "gh": ghd,
            "alerts": alerts(u, p, phases, ghd)}

# ---------------- detail (inspector API) ----------------

def detail(q):
    typ = (q.get("type") or [""])[0]
    t = _T
    if typ == "phase":
        pid = (q.get("id") or [""])[0]
        meta = next((x for x in PHASES if x[0] == pid), None)
        if not meta:
            return {"err": "unknown phase"}
        ev = read_events()
        u = parse_transcript()
        p = project()
        ghd = gh_info()
        phases, explicit = compute_phases(ev, u, p, ghd)
        st = phases.get(pid, {})
        emits = [{"ts": (e.get("ts", "") or "")[11:19], "status": e.get("status", ""),
                  "detail": e.get("detail", "")} for e in ev
                 if e.get("kind") == "phase" and e.get("phase") == pid][-10:]
        senses = [s for s in t["sense_log"] if s["ph"] == pid][-12:]
        pr = None
        if pid == "06" and ghd:
            pr = next((x for x in ghd["prs"] if x["br"] == p["git"]["branch"]), None)
        return {"type": "phase", "id": pid, "name": meta[1], "who": meta[2],
                "state": st, "explicit": pid in explicit, "emits": emits[::-1],
                "senses": senses[::-1], "pr": pr}
    if typ == "agent":
        ats = (q.get("ts") or [""])[0]
        aag = (q.get("agent") or [""])[0]
        for d in reversed(t["delegations"]):
            if d["ts"] == ats and d["agent"] == aag:
                r = _enrich(d, t)
                r.update({"type": "agent", "prompt": d.get("prompt", ""),
                          "report": d.get("report", ""), "file": d.get("file", "")})
                return r
        return {"err": "delegation not found (server restarted?)"}
    if typ == "model":
        name = (q.get("id") or [""])[0]
        m = t["models"].get(name)
        if not m:
            return {"err": "model not seen"}
        pi, po = _price(name)
        cost = (m["in"]*pi + m["cr"]*pi*0.1 + m["cw"]*pi*1.25 + m["out"]*po) / 1e6
        math = [f"input    {m['in']/1e6:9.3f}M × ${pi:5.2f}        = ${m['in']*pi/1e6:8.2f}",
                f"cache rd {m['cr']/1e6:9.3f}M × ${pi*0.1:5.2f} (0.1×) = ${m['cr']*pi*0.1/1e6:8.2f}",
                f"cache wr {m['cw']/1e6:9.3f}M × ${pi*1.25:5.2f} (1.25×)= ${m['cw']*pi*1.25/1e6:8.2f}",
                f"output   {m['out']/1e6:9.3f}M × ${po:5.2f}        = ${m['out']*po/1e6:8.2f}",
                f"total                              = ${cost:8.2f}"]
        users = [{"agent": d["agent"], "desc": d["desc"], "ts": d["ts"]}
                 for d in reversed(t["delegations"])
                 if _short(t["fileuse"].get(d.get("file") or "", {}).get("model", "")) == _short(name)][:10]
        return {"type": "model", "model": name, "short": _short(name), "math": math, "agents": users}
    if typ == "adr":
        fn = (q.get("id") or [""])[0]
        if not re.fullmatch(r"[\w.\-]+\.md", fn or ""):
            return {"err": "bad adr id"}
        f = ROOT / "docs" / "adr" / fn
        try:
            body = f.read_text(encoding="utf-8", errors="replace")
            lines = body.splitlines()
            return {"type": "adr", "title": (lines[0].lstrip('# ').strip() if lines else fn),
                    "body": "\n".join(lines[:60])[:4000]}
        except Exception:
            return {"err": "adr unreadable"}
    if typ == "commit":
        h = (q.get("id") or [""])[0]
        if not re.fullmatch(r"[0-9a-f]{6,40}", h or ""):
            return {"err": "bad hash"}
        body = _git("show", h, "--stat", "--format=%h · %an · %ad%n%s%n%n%b", "--date=format:%d.%m %H:%M")
        return {"type": "commit", "hash": h, "body": "\n".join(body.splitlines()[:40])[:4000] or "not found"}
    if typ == "note":
        nid = (q.get("id") or [""])[0]
        if not re.fullmatch(r"[\w.\-]+", nid or ""):
            return {"err": "bad note id"}
        fn = nid if nid.endswith(".md") else nid + ".md"
        for base in (ROOT / "vault", ROOT / "vault" / "daily",
                     ROOT / "docs" / "arc42", ROOT):
            f = base / fn
            if f.exists() and f.is_file():
                body = f.read_text(errors="replace")
                return {"type": "adr", "title": nid,
                        "body": "\n".join(body.splitlines()[:80])[:5000]}
        return {"err": "note not found"}
    if typ == "gates":
        return {"type": "gates", "list": t["gatehist"][::-1][:25]}
    if typ == "tasks":
        u = parse_transcript()
        return {"type": "tasks", "list": u["todos"]}
    if typ == "errors":
        return {"type": "errors", "n": t["errors"]["n"], "list": t["errors"]["last"][::-1]}
    return {"err": "unknown type"}

# ---------------- UI ----------------

HTML = r"""<!doctype html><html><head><meta charset="utf-8"><title>shipboard — tarifhub</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
:root{--navy:#0C4A6E;--deep:#06263B;--sky:#0EA5E9;--cyan:#22D3EE;--paper:rgba(255,255,255,.92);
--dim:rgba(186,230,253,.75);--faint:rgba(186,230,253,.4);--card:rgba(255,255,255,.05);
--edge:rgba(125,211,252,.18);--ok:#34D399;--run:#FBBF24;--fail:#F87171;--vio:#C4B5FD}
*{box-sizing:border-box}
body{margin:0;padding:22px 30px;background:radial-gradient(1100px 600px at 75% -10%,#0E5A85 0%,var(--navy) 40%,var(--deep) 100%) fixed;
min-height:100vh;font-family:Inter,system-ui,sans-serif;color:var(--paper)}
.wrap{max-width:1560px;margin:0 auto}
.empty{font-size:12px;color:var(--faint);padding:10px;border:1px dashed rgba(125,211,252,.2);border-radius:9px;line-height:1.5}
h1{font-size:26px;font-weight:800;margin:0;display:inline-block}
h1 .slash{color:var(--sky)}
.top{display:flex;align-items:center;gap:18px;margin-bottom:16px;flex-wrap:wrap}
.upd{font-family:'JetBrains Mono';font-size:11px;color:var(--faint)}
.badge{font-family:'JetBrains Mono';font-size:11px;font-weight:600;padding:3px 12px;border-radius:99px;border:1px solid}
.badge.run{color:var(--run);border-color:var(--run)} .badge.ok{color:var(--ok);border-color:var(--ok)}
.badge.fail{color:var(--fail);border-color:var(--fail)} .badge.idle{color:var(--faint);border-color:var(--faint)}
.tabs{margin-left:auto;display:flex;gap:4px}
.tab{font-size:12.5px;font-weight:600;color:var(--dim);padding:6px 14px;border-radius:8px;cursor:pointer;border:1px solid transparent}
.tab:hover{background:var(--card)} .tab.on{background:var(--card);border-color:var(--edge);color:#fff}
.tab .kbd{font-size:9px;color:var(--faint);margin-left:5px;font-family:'JetBrains Mono'}
.grid5{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:12px}
.cell,.panel{background:var(--card);border:1px solid var(--edge);border-radius:12px;padding:11px 14px}
.clk{cursor:pointer} .clk:hover{border-color:rgba(125,211,252,.45)}
.k{font-size:10px;font-weight:600;letter-spacing:.14em;color:var(--faint);text-transform:uppercase}
.v{font-family:'JetBrains Mono';font-size:17px;font-weight:600;margin-top:3px}
.s{font-size:11px;color:var(--dim);margin-top:2px;font-family:'JetBrains Mono'}
.gauge{height:6px;border-radius:3px;background:rgba(255,255,255,.1);margin-top:7px;overflow:hidden}
.gauge i{display:block;height:100%;background:linear-gradient(90deg,var(--sky),var(--cyan))}
.gauge i.warn{background:linear-gradient(90deg,#FBBF24,#F87171)}
.rail{display:grid;grid-template-columns:repeat(9,1fr);gap:6px;margin-bottom:12px}
.step{background:var(--card);border:1px solid var(--edge);border-radius:10px;padding:8px 10px;cursor:pointer;min-width:0}
.step:hover{border-color:rgba(125,211,252,.5)}
.step .sn{font-family:'JetBrains Mono';font-size:10px;color:var(--faint);display:flex;justify-content:space-between;gap:4px;overflow:hidden}
.step .sn span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.step .sn span:first-child{flex-shrink:0}
.step .sl{font-size:12px;font-weight:600;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.step .se{font-family:'JetBrains Mono';font-size:9.5px;color:var(--faint);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.step.pass{border-color:rgba(52,211,153,.4)} .step.pass .sl{color:var(--ok)}
.step.running{border-color:rgba(251,191,36,.55);background:rgba(251,191,36,.07);animation:runglow 2.4s ease-in-out infinite}
.step.running .sl{color:var(--run)}
.step.fail{border-color:rgba(248,113,113,.55)} .step.fail .sl{color:var(--fail)}
@keyframes runglow{0%,100%{box-shadow:0 0 0 0 rgba(251,191,36,0)}50%{box-shadow:0 0 16px 0 rgba(251,191,36,.28)}}
@keyframes rowin{0%{background:rgba(34,211,238,.22);transform:translateX(-5px)}100%{background:transparent;transform:none}}
.feedrow.fresh{animation:rowin 1.1s ease-out}
@keyframes vbump{0%{color:var(--cyan)}100%{color:inherit}}
.v.bump{animation:vbump .9s ease-out}
.sparkdot{animation:pulse 1.4s infinite}
.badge .dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--run);margin-right:6px;animation:pulse 1.4s infinite;vertical-align:1px}
.mid{display:grid;grid-template-columns:1.6fr 1fr;gap:12px;margin-bottom:12px}
.alert{display:flex;gap:8px;font-size:12px;padding:6px 10px;border-radius:8px;margin:4px 0;font-family:'JetBrains Mono'}
.alert.warn{background:rgba(251,191,36,.1);color:var(--run)} .alert.bad{background:rgba(248,113,113,.12);color:var(--fail)}
.alert.none{background:rgba(52,211,153,.08);color:var(--ok)}
.mission{font-size:13px;font-family:'JetBrains Mono';color:var(--paper);margin:8px 0}
.kitem{font-size:11.5px;line-height:1.35;padding:5px 8px;border-radius:7px;background:rgba(255,255,255,.05);
border:1px solid var(--edge);margin-bottom:5px;color:var(--dim)}
.kitem.doing{border-color:rgba(251,191,36,.45);color:var(--paper)}
.kitem.done{opacity:.55}
.kitem .meta{float:right;color:var(--faint);font-family:'JetBrains Mono';font-size:10.5px;margin-left:8px}
.charts{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:12px}
.chart svg{width:100%;height:64px;display:block;margin-top:6px}
.chart .cv{font-family:'JetBrains Mono';font-size:13px;color:var(--paper);float:right}
.kh{font-size:10px;font-weight:600;letter-spacing:.12em;color:var(--faint);text-transform:uppercase;margin-bottom:8px}
.dlg{font-size:11.5px;font-family:'JetBrains Mono';color:var(--dim);margin:5px 0;cursor:pointer;border-radius:6px;padding:2px 4px}
.dlg:hover{background:rgba(255,255,255,.06)}
.dlg b{color:#fff}
.dlg .meta{color:var(--faint);margin-left:6px}
.prow{display:flex;justify-content:space-between;font-size:12.5px;margin:7px 0;gap:10px}
.prow .pk{color:var(--faint)} .prow .pv{font-family:'JetBrains Mono';color:var(--paper);text-align:right}
.pv.warn{color:var(--run)!important} .pv.bad{color:var(--fail)!important} .pv.good{color:var(--ok)!important}
.prow.clk:hover .pk{color:var(--dim)}
.lst{font-size:11.5px;color:var(--dim);margin:4px 0;font-family:'JetBrains Mono';white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lst.clk{cursor:pointer;border-radius:6px;padding:2px 4px} .lst.clk:hover{background:rgba(255,255,255,.06)}
.adrb{font-size:9px;font-weight:600;letter-spacing:.08em;padding:1px 6px;border-radius:4px;margin-right:6px;text-transform:uppercase}
.adrb.acc{background:rgba(52,211,153,.15);color:var(--ok)} .adrb.sup{background:rgba(255,255,255,.08);color:var(--faint)}
.adrb.oth{background:rgba(125,211,252,.12);color:var(--dim)}
.lst.sup{opacity:.45}
table.mt{width:100%;border-collapse:collapse;font-size:12px;font-family:'JetBrains Mono';margin-top:8px}
table.mt th{text-align:left;color:var(--faint);font-size:10px;letter-spacing:.1em;text-transform:uppercase;padding:4px 8px;border-bottom:1px solid var(--edge)}
table.mt td{padding:5px 8px;border-bottom:1px solid rgba(125,211,252,.08);color:var(--dim)}
table.mt td:first-child{color:#fff}
table.mt tr.clk:hover td{background:rgba(255,255,255,.05)}
.phase{display:flex;gap:16px;margin:9px 0;align-items:flex-start}
.num{font-family:'JetBrains Mono';font-size:20px;font-weight:600;color:var(--faint);width:40px;padding-top:13px}
.num.live{color:var(--sky)}
.box{flex:1;background:var(--card);border:1px solid var(--edge);border-radius:13px;padding:12px 16px;cursor:pointer}
.box:hover{border-color:rgba(125,211,252,.5)}
.box.run{border-color:rgba(251,191,36,.5)} .box.fail{border-color:rgba(248,113,113,.5)}
.row{display:flex;align-items:center;gap:12px}
.name{font-weight:600;font-size:15px}
.st{font-family:'JetBrains Mono';font-size:10px;font-weight:600;letter-spacing:.1em;padding:2px 9px;border-radius:4px}
.st.pending{background:rgba(255,255,255,.07);color:var(--faint)}
.st.running{background:rgba(251,191,36,.15);color:var(--run);border:1px solid rgba(251,191,36,.4)}
.st.pass{background:rgba(52,211,153,.15);color:var(--ok)} .st.fail{background:rgba(248,113,113,.15);color:var(--fail)}
.src{font-family:'JetBrains Mono';font-size:9px;color:var(--faint);border:1px solid var(--edge);border-radius:4px;padding:1px 6px}
.ts{margin-left:auto;font-family:'JetBrains Mono';font-size:11px;color:var(--faint)}
.who{font-size:11.5px;color:var(--dim);margin-top:5px;font-family:'JetBrains Mono'}
.detail{font-size:12px;color:var(--dim);margin-top:4px;font-family:'JetBrains Mono'}
.chips{margin:0 0 12px}
.chip{display:inline-block;font-family:'JetBrains Mono';font-size:11.5px;padding:3px 11px;margin:2px 4px 2px 0;cursor:pointer;
border-radius:99px;background:rgba(251,191,36,.08);border:1px solid rgba(251,191,36,.3);color:var(--run)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.45}}
.chip .dot,.kitem .dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--run);margin-right:6px;animation:pulse 1.4s infinite}
.tlpulse{animation:pulse 1.4s infinite}
.kitem.dlgc{border-style:dashed;opacity:.92;cursor:pointer}
.btn{font-size:11.5px;font-weight:600;color:var(--fail);background:none;border:1px solid rgba(248,113,113,.4);
border-radius:8px;padding:5px 12px;cursor:pointer}
.blocks{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:10px 0}
.blk{border:1px solid var(--edge);border-radius:9px;padding:7px 9px;font-size:11px;color:var(--dim)}
.blk b{display:block;font-size:11.5px;color:var(--paper);margin-bottom:2px}
.blk.now{border-color:rgba(251,191,36,.5);background:rgba(251,191,36,.06)}
.blk.done{opacity:.5}
.blk .gauge{margin-top:5px;height:4px}
.foot{font-size:10.5px;color:var(--faint);margin-top:16px;font-family:'JetBrains Mono'}
.view{display:none}.view.on{display:block}
.feedrow{display:flex;gap:10px;align-items:baseline;font-family:'JetBrains Mono';font-size:11.5px;color:var(--dim);
padding:4px 8px;border-bottom:1px solid rgba(125,211,252,.07);cursor:pointer}
.feedrow:hover{background:rgba(255,255,255,.05)}
.feedrow .ft{color:var(--faint);min-width:62px}
.feedrow .fk{min-width:84px;font-size:10px;letter-spacing:.08em;text-transform:uppercase}
.fk.pass{color:var(--ok)} .fk.fail{color:var(--fail)} .fk.running,.fk.active{color:var(--run)} .fk.done{color:var(--vio)}
.feedrow b{color:#fff}
.feedrow .fsrc{margin-left:auto;font-size:9px;color:var(--faint);border:1px solid var(--edge);border-radius:4px;padding:0 5px}
details.raw{margin-top:8px} details.raw summary{font-size:10.5px;color:var(--faint);cursor:pointer;font-family:'JetBrains Mono'}
pre.jl{font-size:10.5px;font-family:'JetBrains Mono';color:var(--dim);background:var(--card);
border:1px solid var(--edge);border-radius:10px;padding:10px 12px;overflow-x:auto}
.mdh{font-weight:600;color:#fff;margin:6px 0 3px;font-family:Inter}
.mdli{margin:2px 0 2px 10px}
.mdwrap code{background:rgba(255,255,255,.08);border-radius:4px;padding:0 4px}
.cirow{display:flex;gap:10px;font-family:'JetBrains Mono';font-size:11.5px;color:var(--dim);margin:4px 0}
.cirow .ok{color:var(--ok)} .cirow .bad{color:var(--fail)} .cirow .pend{color:var(--run)}
.flag{display:inline-block;font-family:'JetBrains Mono';font-size:10.5px;margin:2px 8px 2px 0;color:var(--dim)}
.flag.on{color:var(--ok)} .flag.off{color:var(--fail)}
.hbar{display:flex;align-items:center;gap:8px;font-family:'JetBrains Mono';font-size:10.5px;color:var(--dim);margin:3px 0}
.hbar .hn{min-width:86px;text-align:right;color:var(--faint)}
.hbar .hb{height:8px;border-radius:4px;background:linear-gradient(90deg,var(--sky),var(--cyan))}
/* inspector drawer */
#ovl{position:fixed;inset:0;background:rgba(2,16,28,.5);display:none;z-index:9}
#insp{position:fixed;top:0;right:-560px;width:540px;max-width:92vw;height:100vh;z-index:10;
background:linear-gradient(180deg,#0A3A57,#06263B);border-left:1px solid rgba(125,211,252,.3);
box-shadow:-18px 0 50px rgba(0,0,0,.45);transition:right .18s ease;display:flex;flex-direction:column}
#insp.on{right:0}
#insp .ih{display:flex;align-items:center;gap:10px;padding:16px 20px;border-bottom:1px solid var(--edge)}
#insp .ih .it{font-weight:800;font-size:16px}
#insp .ih .ix{margin-left:auto;cursor:pointer;color:var(--faint);font-size:18px;padding:2px 8px;border-radius:6px}
#insp .ih .ix:hover{background:var(--card);color:#fff}
#insp .ib{padding:14px 20px;overflow-y:auto;flex:1}
.pre{font-family:'JetBrains Mono';font-size:11px;color:var(--dim);background:rgba(0,0,0,.25);
border:1px solid var(--edge);border-radius:9px;padding:10px 12px;white-space:pre-wrap;word-break:break-word;
max-height:340px;overflow-y:auto;margin:6px 0 12px}
.itag{display:inline-block;font-family:'JetBrains Mono';font-size:10px;padding:2px 9px;border-radius:5px;
background:rgba(125,211,252,.1);border:1px solid var(--edge);color:var(--dim);margin:0 6px 6px 0}
</style></head><body><div class="wrap">
<div class="top">
  <h1><span class="slash">/ship</span> shipboard</h1>
  <span class="badge idle" id="badge">IDLE</span>
  <span class="upd" id="upd"></span>
  <div class="tabs">
    <div class="tab on" data-v="overview">Overview<span class="kbd">1</span></div>
    <div class="tab" data-v="pipeline">Pipeline<span class="kbd">2</span></div>
    <div class="tab" data-v="agents">Agents<span class="kbd">3</span></div>
    <div class="tab" data-v="project">Project<span class="kbd">4</span></div>
    <div class="tab" data-v="graphs">Graphs<span class="kbd">5</span></div>
  </div>
</div>

<div class="view on" id="v-overview">
  <div class="grid5">
    <div class="cell"><div class="k">Session</div><div class="v" id="sess">—</div><div class="s" id="sess2"></div></div>
    <div class="cell"><div class="k">Context</div><div class="v" id="ctx">—</div><div class="gauge"><i id="ctxbar" style="width:0%"></i></div><div class="s" id="ctx2"></div></div>
    <div class="cell"><div class="k">Tokens in / out</div><div class="v" id="tok">—</div><div class="s" id="tok2"></div></div>
    <div class="cell"><div class="k">Est. cost (USD)</div><div class="v" id="cost">—</div><div class="s" id="cost2"></div></div>
    <div class="cell"><div class="k">CAS countdown</div><div class="v" id="cas">—</div><div class="s" id="cas2"></div></div>
  </div>
  <div class="rail" id="rail"></div>
  <div class="chips" id="chips" style="display:none"></div>
  <div class="mid">
    <div class="panel">
      <div class="k">Mission · in progress now</div>
      <div class="mission" id="mission">—</div>
      <div id="doing"></div>
      <div class="k" style="margin-top:10px">Live feed</div>
      <div id="minifeed">—</div>
    </div>
    <div class="panel">
      <div class="k">Alerts</div>
      <div id="alerts"></div>
      <div class="k" style="margin-top:12px">Vitals</div>
      <div class="prow"><span class="pk">Branch</span><span class="pv" id="branch">—</span></div>
      <div class="prow"><span class="pk">Working tree</span><span class="pv" id="dirty">—</span></div>
      <div class="prow clk" onclick="inspect('gates')" title="click: gate history"><span class="pk">Tests (last gate) ▸</span><span class="pv" id="tests">—</span></div>
      <div class="prow clk" onclick="inspect('tasks')" title="click: full task list"><span class="pk">Tasks ▸</span><span class="pv" id="taskline">—</span></div>
      <div class="prow clk" onclick="inspect('errors')" title="click: last tool errors"><span class="pk">Tool errors ▸</span><span class="pv" id="errn">—</span></div>
      <div class="prow"><span class="pk">Journal today</span><span class="pv" id="journal">—</span></div>
      <div class="k" style="margin-top:12px">Tool activity</div>
      <div id="thist">—</div>
    </div>
  </div>
  <div class="charts">
    <div class="panel chart"><span class="k">Context over turns</span><span class="cv" id="c1v"></span><svg id="c1" preserveAspectRatio="none"></svg></div>
    <div class="panel chart"><span class="k">Est. cost over turns</span><span class="cv" id="c2v"></span><svg id="c2" preserveAspectRatio="none"></svg></div>
    <div class="panel chart"><span class="k">Output tokens (cum.)</span><span class="cv" id="c3v"></span><svg id="c3" preserveAspectRatio="none"></svg></div>
  </div>
</div>

<div class="view" id="v-pipeline">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <div class="k">9-phase pipeline — click any phase for its evidence · state source: emit &gt; gh &gt; sensed</div>
    <button class="btn" onclick="resetRun()">reset run state</button>
  </div>
  <div id="runhint" class="empty" style="display:none;margin-bottom:8px"></div>
  <div id="phasesFull"></div>
  <div class="mid" style="margin-top:14px">
    <div class="panel">
      <div class="k">Activity feed (hooks ∪ transcript) — click a row for the agent</div>
      <div id="evfeed">—</div>
      <details class="raw"><summary>raw event log</summary><pre class="jl" id="evlog">—</pre></details>
    </div>
    <div>
      <div class="panel" style="margin-bottom:12px">
        <div class="k">PR &amp; CI (live via gh)</div>
        <div id="ghpanel" class="s">—</div>
      </div>
      <div class="panel clk" onclick="inspect('gates')">
        <div class="k">Gate history ▸</div>
        <div id="gh8" class="s">—</div>
      </div>
    </div>
  </div>
</div>

<div class="view" id="v-agents">
  <div class="mid">
    <div class="panel">
      <div class="k">Per-model usage &amp; cost (main + subagents) — click a row for the math</div>
      <table class="mt"><thead><tr><th>model</th><th>in</th><th>cache r/w</th><th>out</th><th>est. $</th></tr></thead><tbody id="mtb"></tbody></table>
      <div class="s" style="margin-top:8px" id="sessmeta"></div>
    </div>
    <div class="panel">
      <div class="k">Session</div>
      <div class="prow"><span class="pk">Status</span><span class="pv" id="ss1">—</span></div>
      <div class="prow"><span class="pk">Started · duration</span><span class="pv" id="ss2">—</span></div>
      <div class="prow"><span class="pk">Turns / prompts / tools</span><span class="pv" id="ss4">—</span></div>
      <div class="prow"><span class="pk">Compactions</span><span class="pv" id="ss5">—</span></div>
      <div class="prow"><span class="pk">Cache hit · saved</span><span class="pv" id="ss6">—</span></div>
      <div class="prow"><span class="pk">Side-sessions · matched</span><span class="pv" id="ss7">—</span></div>
      <div class="prow"><span class="pk">Cost main / subagents</span><span class="pv" id="ss8">—</span></div>
      <div class="prow"><span class="pk">Burn rate</span><span class="pv" id="ss9">—</span></div>
    </div>
  </div>
  <div class="panel" style="margin-bottom:12px">
    <div class="k">Delegation timeline (local time) — click a bar</div>
    <div id="tl" style="margin-top:8px">—</div>
  </div>
  <div class="panel">
    <div class="k">Agents — every delegation this session · click a row for prompt, report &amp; cost</div>
    <table class="mt"><thead><tr><th>when</th><th>agent</th><th>model</th><th>task</th><th>time</th><th>tokens in/out</th><th>est. $</th><th>status</th></tr></thead><tbody id="atb"></tbody></table>
  </div>
</div>

<div class="view" id="v-project">
  <div class="mid">
    <div class="panel">
      <div class="k">CAS plan — <span id="blockNow" style="color:var(--run)"></span></div>
      <div class="blocks" id="blocks"></div>
      <div class="k" style="margin-top:12px">Recent commits — click for the diffstat</div>
      <div id="commits"></div>
      <div class="k" style="margin-top:12px">Journal today <span id="jcount" style="text-transform:none;letter-spacing:0"></span></div>
      <div id="jprev" class="mdwrap" style="max-height:260px;overflow-y:auto;font-size:11.5px;color:var(--dim);font-family:'JetBrains Mono';line-height:1.55;margin-top:6px">—</div>
    </div>
    <div>
      <div class="panel" style="margin-bottom:12px">
        <div class="k">Evidence pulse</div>
        <div class="prow clk" onclick="inspect('gates')"><span class="pk">Tests (last gate run) ▸</span><span class="pv" id="ev1">—</span></div>
        <div class="prow"><span class="pk">Journal entries (crit. 15)</span><span class="pv" id="ev2">—</span></div>
        <div class="prow"><span class="pk">Fazit observations</span><span class="pv" id="ev3">—</span></div>
        <div class="prow"><span class="pk">LEARNINGS items (crit. 9)</span><span class="pv" id="ev4">—</span></div>
        <div id="flags" style="margin-top:6px">—</div>
        <div class="k" style="margin-top:10px">CI runs (gh)</div>
        <div id="ciruns" class="s">—</div>
      </div>
      <div class="panel" style="margin-bottom:12px">
        <div class="k">Repo shape (src / test files)</div>
        <div id="svc">—</div>
      </div>
      <div class="panel">
        <div class="k">Architecture decisions (<span id="adrn2">0</span>) — click to read</div>
        <div id="adrlist"></div>
      </div>
    </div>
  </div>
</div>

<div class="view" id="v-graphs">
  <div class="panel" style="margin-bottom:12px">
    <span class="s" id="vgmeta" style="float:right"></span>
    <div class="k">Second brain — vault link graph · wheel: zoom · drag: pan · click: read · double-click: reset</div>
    <canvas id="vgc" style="width:100%;height:460px;margin-top:8px;display:block"></canvas>
  </div>
  <div class="panel">
    <div class="k">Code graph — graphify (interactive: click, filter, search) · <a href="/graphify" target="_blank" style="color:var(--sky)">open standalone ↗</a></div>
    <iframe id="gfframe" style="width:100%;height:560px;border:1px solid var(--edge);border-radius:10px;background:#fff;margin-top:8px"></iframe>
  </div>
</div>

<div class="foot">shipboard v8.3 · one file · stdlib · click anything for its evidence · data: /ship emits + hooks + transcripts (sidechain x-ray, UTC→local) + gh + repo + vault wikilinks + graphify · keys: 1-5 tabs, Esc closes inspector</div>
</div>
<div id="ovl" onclick="closeInsp()"></div>
<div id="insp"><div class="ih"><span class="it" id="it">inspector</span><span class="ix" onclick="closeInsp()">✕</span></div><div class="ib" id="ib">—</div></div>
<script>
const PH = %PHASES%;
const fmt = n => n>=1e6 ? (n/1e6).toFixed(2)+'M' : n>=1e3 ? (n/1e3).toFixed(1)+'k' : ''+n;
const esc = t => (''+(t??'')).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const fdur = s => s==null?'':(s<90?s+'s':(s<5400?Math.round(s/60)+'m':(Math.floor(s/3600)+'h'+String(Math.round(s%3600/60)).padStart(2,'0'))));
const tsec = t=>{const q=(t||'').split(':'); return q.length===3? +q[0]*3600+ +q[1]*60+ +q[2] : null;};
const nowsec = ()=>{const n=new Date(); return n.getHours()*3600+n.getMinutes()*60+n.getSeconds();};
const elapsed = ts => { const a=tsec(ts); if(a==null) return '';
  let s=nowsec()-a; if(s<0) s+=86400; if(s>43200) return ''; return fdur(s); };
const mdlite = t => esc(t).replace(/\*\*([^*]+)\*\*/g,'<b style="color:#fff">$1</b>').replace(/`([^`]+)`/g,'<code>$1</code>')
  .split('\n').map(l=>/^#+ /.test(l)?'<div class="mdh">'+l.replace(/^#+ /,'')+'</div>':(/^- /.test(l)?'<div class="mdli">• '+l.slice(2)+'</div>':(l?'<div>'+l+'</div>':''))).join('');
let S0=null;
function showTab(v){
  document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x.dataset.v===v));
  document.querySelectorAll('.view').forEach(x=>x.classList.remove('on'));
  document.getElementById('v-'+v).classList.add('on');
  if(v==='graphs') loadGraphs();
}
document.querySelectorAll('.tab').forEach(el=>el.onclick=()=>showTab(el.dataset.v));
document.addEventListener('keydown',e=>{
  if(e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA') return;
  if(e.key==='Escape') closeInsp();
  const m={'1':'overview','2':'pipeline','3':'agents','4':'project','5':'graphs'}[e.key];
  if(m) showTab(m);
});
// ---------- graphs tab: vault wikilink graph (canvas force layout) + graphify iframe ----------
let VGanim=null;
function drawVG(g){
  const cv=document.getElementById('vgc'); if(!cv) return;
  const W=cv.clientWidth||1100, H=460;
  cv.width=W*devicePixelRatio; cv.height=H*devicePixelRatio;
  const ctx=cv.getContext('2d');
  const N=g.nodes||[], E=g.edges||[], idx={};
  N.forEach((n,i)=>idx[n.id]=i);
  if(VGanim) cancelAnimationFrame(VGanim);
  if(!N.length){ctx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);
    ctx.fillStyle='rgba(186,230,253,.4)';ctx.font='12px JetBrains Mono';
    ctx.fillText('vault empty — notes appear as the second brain grows',24,44);return;}
  const deg={};
  E.forEach(e=>{deg[e[0]]=(deg[e[0]]||0)+1; deg[e[1]]=(deg[e[1]]||0)+1;});
  N.forEach(n=>{n.d=deg[n.id]||0; n.r=n.t==='hub'?10:4+Math.min(5,1.5*Math.sqrt(n.d));});
  const ang={adr:0.9,arc:2.7,journal:4.3,reflect:5.5};
  N.forEach((n,i)=>{const a=(ang[n.t]??(i*0.7))+(i%9)*0.14;
    const r=n.t==='hub'?0:110+(i%6)*22;
    n.x=W/2+Math.cos(a)*r; n.y=H/2+Math.sin(a)*r*0.55; n.vx=0; n.vy=0;});
  const hubId=(N.find(n=>n.t==='hub')||{}).id;
  const col={hub:'#0EA5E9',adr:'#C4B5FD',journal:'#34D399',reflect:'#FBBF24',arc:'#22D3EE'};
  // view transform: screen = world*s + (ox,oy) — wheel zooms toward cursor, drag pans
  let s=1, ox=0, oy=0, alpha=1, hover=null, drag=null, moved=0;
  const toWorld=(x,y)=>[(x-ox)/s,(y-oy)/s];
  function step(){
    if(alpha>0.028){
      for(let i=0;i<N.length;i++)for(let j=i+1;j<N.length;j++){
        const a=N[i],b=N[j]; let dx=a.x-b.x,dy=a.y-b.y; let d2=dx*dx+dy*dy; if(d2<1)d2=1;
        if(d2<36000){const f=820/d2*alpha; a.vx+=dx*f;a.vy+=dy*f;b.vx-=dx*f;b.vy-=dy*f;}}
      E.forEach(e=>{const a=N[idx[e[0]]],b=N[idx[e[1]]]; if(!a||!b)return;
        const hub=(e[0]===hubId||e[1]===hubId);
        let dx=b.x-a.x,dy=b.y-a.y; const d=Math.sqrt(dx*dx+dy*dy)||1;
        const f=(d-(hub?175:72))*(hub?0.0045:0.03)*alpha;
        a.vx+=dx/d*f;a.vy+=dy/d*f;b.vx-=dx/d*f;b.vy-=dy/d*f;});
      N.forEach(n=>{n.vx+=(W/2-n.x)*0.0035*alpha; n.vy+=(H/2-n.y)*0.007*alpha;
        n.vx*=0.58;n.vy*=0.58; n.x+=n.vx;n.y+=n.vy;
        n.x=Math.max(16,Math.min(W-16,n.x)); n.y=Math.max(14,Math.min(H-14,n.y));});
      alpha*=0.985;            // settles, then HOLDS STILL — stable click targets
    }
    ctx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);
    ctx.clearRect(0,0,W,H);
    ctx.translate(ox,oy); ctx.scale(s,s);
    let hl=null;
    if(hover){hl=new Set([hover.id]);
      E.forEach(e=>{if(e[0]===hover.id)hl.add(e[1]); if(e[1]===hover.id)hl.add(e[0]);});}
    E.forEach(e=>{const a=N[idx[e[0]]],b=N[idx[e[1]]]; if(!a||!b)return;
      const on=hover&&(e[0]===hover.id||e[1]===hover.id);
      const hub=(e[0]===hubId||e[1]===hubId);
      ctx.strokeStyle=on?'rgba(34,211,238,.75)':(hub?'rgba(125,211,252,.08)':'rgba(125,211,252,.30)');
      ctx.lineWidth=(on?1.5:1)/s;
      ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();});
    const drawn=[];
    N.forEach(n=>{const dim=hl&&!hl.has(n.id);
      ctx.globalAlpha=dim?0.22:1;
      ctx.fillStyle=col[n.t]||'#94A3B8';
      ctx.beginPath();ctx.arc(n.x,n.y,n.r,0,6.283);ctx.fill();
      if(n.t==='hub'){ctx.strokeStyle='rgba(255,255,255,.5)';ctx.lineWidth=1/s;ctx.stroke();}
      const want=(n.t==='hub')||(hl&&hl.has(n.id))||(!hl&&(n.d>=2||N.length<=26||s>1.6));
      if(want){const fs=Math.max(6.5,9.5/Math.sqrt(s)); const lx=n.x+n.r+4, ly=n.y+3;
        if(!drawn.some(p=>Math.abs(p[0]-lx)<76/s&&Math.abs(p[1]-ly)<11/s)){
          ctx.font=fs+'px JetBrains Mono';
          ctx.fillStyle=dim?'rgba(231,244,255,.2)':'rgba(231,244,255,.85)';
          ctx.fillText((n.label||n.id).slice(0,s>1.6?40:24),lx,ly); drawn.push([lx,ly]);}}
      ctx.globalAlpha=1;});
    const view=document.getElementById('v-graphs');
    if(view && view.classList.contains('on')) VGanim=requestAnimationFrame(step);
  }
  step();
  const near=(x,y)=>{const [wx,wy]=toWorld(x,y); let best=null,bd=1e9;
    N.forEach(n=>{const d=Math.hypot(n.x-wx,n.y-wy); if(d<bd){bd=d;best=n;}});
    return (best&&bd<=best.r+12/s)?best:null;};
  cv.onwheel=ev=>{ev.preventDefault();
    const r=cv.getBoundingClientRect(), x=ev.clientX-r.left, y=ev.clientY-r.top;
    const f=ev.deltaY<0?1.13:0.885, ns=s*f;
    if(ns<0.35||ns>7) return;
    ox=x-(x-ox)*f; oy=y-(y-oy)*f; s=ns;};
  cv.onmousedown=ev=>{const r=cv.getBoundingClientRect();
    drag={x:ev.clientX-r.left,y:ev.clientY-r.top}; moved=0;};
  cv.onmousemove=ev=>{const r=cv.getBoundingClientRect();
    const x=ev.clientX-r.left, y=ev.clientY-r.top;
    if(drag){ox+=x-drag.x; oy+=y-drag.y; moved+=Math.abs(x-drag.x)+Math.abs(y-drag.y);
      drag={x,y}; cv.style.cursor='grabbing'; return;}
    hover=near(x,y); cv.style.cursor=hover?'pointer':'default';};
  cv.onmouseup=ev=>{const r=cv.getBoundingClientRect();
    const wasDrag=moved>5; drag=null; cv.style.cursor='default';
    if(wasDrag) return;
    const n=near(ev.clientX-r.left, ev.clientY-r.top);
    if(n) inspect(n.t==='adr'?'adr':'note', n.f||n.id);};
  cv.onmouseleave=()=>{hover=null; drag=null;};
  cv.ondblclick=()=>{s=1;ox=0;oy=0;};
}
async function loadGraphs(){
  try{
    const g=await (await fetch('/vaultgraph')).json();
    drawVG(g);
    document.getElementById('vgmeta').textContent=(g.nodes||[]).length+' notes · '+(g.edges||[]).length+' links · rebuilt '+(g.updated||'');
  }catch(e){}
  const fr=document.getElementById('gfframe');
  if(fr && !fr.getAttribute('src')) fr.src='/graphify';
}
// ---------- inspector ----------
function closeInsp(){document.getElementById('insp').classList.remove('on');document.getElementById('ovl').style.display='none';}
async function inspect(type,a,b){
  const q = type==='phase'?('type=phase&id='+a)
    : type==='agent'?('type=agent&ts='+encodeURIComponent(a)+'&agent='+encodeURIComponent(b))
    : type==='model'?('type=model&id='+encodeURIComponent(a))
    : type==='adr'?('type=adr&id='+encodeURIComponent(a))
    : type==='commit'?('type=commit&id='+encodeURIComponent(a))
    : ('type='+type);
  let d; try{ d = await (await fetch('/detail?'+q)).json(); }catch(e){ d={err:'fetch failed'}; }
  const it=document.getElementById('it'), ib=document.getElementById('ib');
  if(d.err){ it.textContent='inspector'; ib.innerHTML='<div class="empty">'+esc(d.err)+'</div>'; }
  else if(d.type==='phase'){
    const st=d.state||{};
    it.innerHTML='Phase '+esc(d.id)+' — '+esc(d.name);
    ib.innerHTML='<span class="itag">'+esc(st.status||'pending')+'</span><span class="itag">source: '+esc(st.src||'—')+'</span>'+
      (st.ts?'<span class="itag">'+esc(st.ts)+'</span>':'')+(d.explicit?'<span class="itag">explicit emit</span>':'')+
      '<div class="s" style="margin:8px 0 4px">'+esc(d.who)+'</div>'+
      (st.detail?'<div class="pre">'+esc(st.detail)+'</div>':'')+
      (d.pr?'<div class="k" style="margin-top:8px">PR on this branch</div><div class="cirow"><b>#'+d.pr.n+'</b><span class="ok">'+d.pr.ok+'✓</span>'+(d.pr.fail?'<span class="bad">'+d.pr.fail+'✗</span>':'')+(d.pr.pend?'<span class="pend">'+d.pr.pend+'◌</span>':'')+'<span>'+esc(d.pr.t)+'</span></div>':'')+
      '<div class="k" style="margin-top:10px">Explicit emits ('+d.emits.length+')</div>'+
      (d.emits.length?d.emits.map(e=>'<div class="dlg">'+esc(e.ts)+' · <b>'+esc(e.status)+'</b> — '+esc(e.detail)+'</div>').join(''):'<div class="s">none — this phase was never explicitly emitted</div>')+
      '<div class="k" style="margin-top:10px">Sensing audit trail ('+d.senses.length+')</div>'+
      (d.senses.length?d.senses.map(e=>'<div class="dlg">'+esc(e.ts)+' · <b>'+esc(e.st)+'</b> — '+esc(e.d)+'</div>').join(''):'<div class="s">no transcript observations for this phase</div>');
  } else if(d.type==='agent'){
    it.innerHTML=esc(d.agent)+' <span style="color:var(--faint);font-weight:400">'+esc(d.model||'')+'</span>';
    ib.innerHTML='<span class="itag">'+(d.live?'⟲ live '+elapsed(d.ts):'✓ done')+'</span><span class="itag">'+esc(d.ts)+(d.done_ts?' → '+esc(d.done_ts):'')+'</span>'+
      (d.dur_s!=null?'<span class="itag">'+fdur(d.dur_s)+'</span>':'')+
      (d.cost!=null?'<span class="itag">$'+d.cost.toFixed(2)+'</span>':'<span class="itag">cost n/a (unmatched sidechain)</span>')+
      (d.tin!=null?'<span class="itag">'+fmt(d.tin)+' in / '+fmt(d.tout)+' out</span>':'')+
      '<div class="k" style="margin-top:8px">Task</div><div class="pre" style="max-height:80px">'+esc(d.desc)+'</div>'+
      '<div class="k">Dispatch prompt</div><div class="pre">'+esc(d.prompt||'—')+'</div>'+
      '<div class="k">Returned report</div><div class="pre">'+esc(d.report||(d.live?'still running…':'no report captured (dispatched before v8 or server restarted after return)'))+'</div>'+
      (d.file?'<div class="s">sidechain: '+esc(d.file.split('/').slice(-2).join('/'))+'</div>':'<div class="s">no sidechain transcript matched</div>');
  } else if(d.type==='model'){
    it.innerHTML=esc(d.short)+' <span style="color:var(--faint);font-weight:400">'+esc(d.model)+'</span>';
    ib.innerHTML='<div class="k">Cost math (prices in shipboard.py)</div><div class="pre">'+esc(d.math.join('\n'))+'</div>'+
      '<div class="k">Delegations on this model</div>'+
      (d.agents.length?d.agents.map(a=>'<div class="dlg" onclick="inspect(\'agent\',\''+esc(a.ts)+'\',\''+esc(a.agent)+'\')">'+esc(a.ts)+' · <b>'+esc(a.agent)+'</b> — '+esc(a.desc)+'</div>').join(''):'<div class="s">main session only</div>');
  } else if(d.type==='adr'){
    it.textContent=d.title; ib.innerHTML='<div class="mdwrap" style="font-size:12px;line-height:1.6">'+mdlite(d.body)+'</div>';
  } else if(d.type==='commit'){
    it.textContent='commit '+d.hash; ib.innerHTML='<div class="pre" style="max-height:70vh">'+esc(d.body)+'</div>';
  } else if(d.type==='gates'){
    it.textContent='Gate history';
    ib.innerHTML=d.list.length?d.list.map(g=>'<div class="dlg">'+esc(g.ts)+' · <b style="color:'+(g.ok?'var(--ok)':'var(--fail)')+'">'+esc(g.kind)+'</b>'+
      (g.passed!=null?' — '+g.passed+' passed'+(g.failed?' · <span style="color:var(--fail)">'+g.failed+' failed</span>':''):(g.ok?' — clean':' — errors'))+
      (g.cmd?'<span class="meta">'+esc(g.cmd)+'</span>':'')+'</div>').join(''):'<div class="empty">no ruff/pytest results observed yet</div>';
  } else if(d.type==='tasks'){
    it.textContent='Session task list';
    const G={pending:[],in_progress:[],completed:[]};
    (d.list||[]).forEach(t=>(G[t.status]||G.pending).push(t));
    ib.innerHTML=['in_progress','pending','completed'].map(k=>'<div class="k" style="margin-top:8px">'+k.replace('_',' ')+' · '+G[k].length+'</div>'+
      (G[k].map(t=>'<div class="kitem'+(k==='in_progress'?' doing':(k==='completed'?' done':''))+'">'+(k==='completed'?'✓ ':'')+esc(t.content)+'</div>').join('')||'<div class="s">none</div>')).join('')
      ||'<div class="empty">no task list this session</div>';
  } else if(d.type==='errors'){
    it.textContent='Tool errors · '+d.n;
    ib.innerHTML=(d.list&&d.list.length)?d.list.map(e=>'<div class="k" style="margin-top:8px">'+esc(e.ts)+'</div><div class="pre" style="max-height:120px">'+esc(e.txt)+'</div>').join(''):'<div class="empty">no tool errors recorded</div>';
  } else { it.textContent='inspector'; ib.innerHTML='<div class="empty">nothing here</div>'; }
  document.getElementById('ovl').style.display='block';
  document.getElementById('insp').classList.add('on');
}
function spark(id, pts, key, color){
  const svg = document.getElementById(id); if(!svg) return;
  const W=300,H=64; svg.setAttribute('viewBox','0 0 '+W+' '+H);
  if(!pts || pts.length<2){ svg.innerHTML='<text x="6" y="36" fill="rgba(186,230,253,.35)" font-size="11">waiting for turns…</text>'; return; }
  const vals = pts.map(p=>p[key]); const mx = Math.max(...vals)||1;
  const xs = i => 4 + i*(W-8)/(pts.length-1);
  const ys = v => H-6 - (v/mx)*(H-16);
  const line = pts.map((p,i)=>(i?'L':'M')+xs(i).toFixed(1)+','+ys(p[key]).toFixed(1)).join(' ');
  const lx=xs(pts.length-1).toFixed(1), ly=ys(pts[pts.length-1][key]).toFixed(1);
  svg.innerHTML = '<path d="'+line+' L'+lx+','+(H-4)+' L4,'+(H-4)+' Z" fill="'+color+'22"/>' +
                  '<path d="'+line+'" fill="none" stroke="'+color+'" stroke-width="1.8"/>' +
                  '<circle cx="'+lx+'" cy="'+ly+'" r="2.8" fill="'+color+'" class="sparkdot"/>';
}
let lastFeedTs=null;
function setV(id, txt){
  const el=document.getElementById(id); if(!el) return;
  if(el.textContent!==txt){ el.textContent=txt; el.classList.remove('bump'); void el.offsetWidth; el.classList.add('bump'); }
}
function timeline(dl){
  const el=document.getElementById('tl'); if(!el) return;
  const rows=dl.slice(0,18).reverse();
  if(!rows.length){ el.innerHTML='<div class="empty">delegations appear here as time bars — dispatch to return, live ones pulse</div>'; return; }
  const ns=nowsec();
  let mn=Infinity, mx=0;
  rows.forEach(d=>{const a=tsec(d.ts); if(a==null) return;
    let b=d.live?ns:(d.dur_s!=null?a+d.dur_s:a+60); if(b<a)b+=86400;
    mn=Math.min(mn,a); mx=Math.max(mx,b);});
  if(!isFinite(mn)){ el.innerHTML='<div class="empty">no timestamps yet</div>'; return; }
  mx=Math.max(mx,mn+300);
  const W=1200,RH=21,L=170,H=rows.length*RH+26;
  const X=s=>L+(s-mn)/(mx-mn)*(W-L-110);
  const col=a=>a==='implementer'?'#0EA5E9':(a==='e2e-tester'?'#34D399':(a==='codex-reviewer'?'#FBBF24':'#C4B5FD'));
  let step=1800; const span=mx-mn; if(span<=1800)step=300; else if(span<=5400)step=900;
  let svg='<svg viewBox="0 0 '+W+' '+H+'" style="width:100%;height:'+H+'px">';
  for(let s2=Math.ceil(mn/step)*step;s2<=mx;s2+=step){const x=X(s2);
    svg+='<line x1="'+x+'" y1="16" x2="'+x+'" y2="'+(H-4)+'" stroke="rgba(125,211,252,.12)"/>'+
         '<text x="'+x+'" y="11" fill="rgba(186,230,253,.4)" font-size="9" text-anchor="middle" font-family="JetBrains Mono">'+
         String(Math.floor(s2/3600)%24).padStart(2,'0')+':'+String(Math.floor((s2%3600)/60)).padStart(2,'0')+'</text>';}
  rows.forEach((d,i)=>{const a=tsec(d.ts); if(a==null) return;
    let b=d.live?ns:(d.dur_s!=null?a+d.dur_s:a+60); if(b<a)b+=86400;
    const y=20+i*RH, c=col(d.agent);
    const onc=' onclick="inspect(\'agent\',\''+esc(d.ts)+'\',\''+esc(d.agent)+'\')" style="cursor:pointer"';
    svg+='<text x="'+(L-8)+'" y="'+(y+10)+'" fill="rgba(186,230,253,.75)" font-size="10" text-anchor="end" font-family="JetBrains Mono"'+onc+'>'+esc(d.agent)+'</text>';
    svg+='<rect x="'+X(a).toFixed(1)+'" y="'+y+'" width="'+Math.max(3,X(b)-X(a)).toFixed(1)+'" height="13" rx="3" fill="'+c+(d.live?'':'77')+'"'+(d.live?' class="tlpulse"':'')+onc+'><title>'+esc(d.desc)+'</title></rect>';
    const lab=(d.live?'live '+fdur(Math.max(0,ns-a)):fdur(d.dur_s))+(d.cost!=null?' · $'+d.cost.toFixed(2):'');
    svg+='<text x="'+(X(b)+5).toFixed(1)+'" y="'+(y+10)+'" fill="rgba(186,230,253,.55)" font-size="9.5" font-family="JetBrains Mono">'+esc(lab)+'</text>';});
  el.innerHTML=svg+'</svg>';
}
async function resetRun(){ if(confirm('Clear pipeline run state (events.jsonl + sensed phases)?')) await fetch('/reset',{method:'POST'}); }
function dlgRow(d){
  const m=d.model?' <span class="meta">'+esc(d.model)+'</span>':'';
  const tail=d.live?' <span class="meta" style="color:var(--run)">⟲ live '+elapsed(d.ts)+'</span>'
    :(d.done?' <span class="meta">✓'+(d.dur_s!=null?' '+fdur(d.dur_s):'')+(d.cost!=null?' · $'+d.cost.toFixed(2):'')+'</span>':'');
  return '<div class="dlg" onclick="inspect(\'agent\',\''+esc(d.ts)+'\',\''+esc(d.agent)+'\')">'+(d.ts?d.ts+' · ':'')+'<b>'+esc(d.agent)+'</b> — '+esc(d.desc)+m+tail+'</div>';
}
function feedRow(e, fresh){
  const lbl=e.kind==='agent'?(e.status==='active'?'dispatch':'return'):('ph '+e.phase+' '+e.status);
  const cls=e.kind==='agent'?(e.status==='active'?'active':'done'):e.status;
  const body=e.kind==='agent'?'<b>'+esc(e.agent)+'</b>'+(e.model?' · '+esc(e.model):'')+(e.detail?' — '+esc(e.detail):''):esc(e.detail||'');
  const onc=e.kind==='agent'?' onclick="inspect(\'agent\',\''+esc(e.ts)+'\',\''+esc(e.agent)+'\')"':(e.phase?' onclick="inspect(\'phase\',\''+esc(e.phase)+'\')"':'');
  return '<div class="feedrow'+(fresh?' fresh':'')+'"'+onc+'><span class="ft">'+esc(e.ts)+'</span><span class="fk '+esc(cls)+'">'+esc(lbl)+'</span><span>'+body+'</span><span class="fsrc">'+esc(e.src||'')+'</span></div>';
}
async function tick(){
  let s; try { s = await (await fetch('/state')).json(); }
  catch(e){ const b=document.getElementById('badge'); b.textContent='SERVER UNREACHABLE'; b.className='badge fail';
            document.getElementById('upd').textContent='connection lost — restart shipboard.py'; return; }
  S0=s;
  document.getElementById('upd').textContent='updated '+s.updated+' · '+s.events+' events';
  const u=s.usage, p=s.project;
  const sts = Object.values(s.phases).map(x=>x.status);
  const badge = document.getElementById('badge');
  if (sts.includes('fail')) { badge.textContent='ATTENTION'; badge.className='badge fail'; }
  else if (sts.includes('running')||s.active.length) { badge.innerHTML='<span class="dot"></span>RUNNING'; badge.className='badge run'; }
  else if (s.phases['09'] && s.phases['09'].status==='pass') { badge.textContent='SHIPPED'; badge.className='badge ok'; }
  else if (u.session.status==='active') { badge.innerHTML='<span class="dot"></span>SESSION ACTIVE'; badge.className='badge run'; }
  else { badge.textContent='IDLE'; badge.className='badge idle'; }
  const idle = u.idle_sec>120 ? ' · idle '+fdur(u.idle_sec) : ' · live';
  document.getElementById('sess').textContent = u.tracked ? (u.session.status.toUpperCase()+(u.session.id?' · '+u.session.id:'')) : 'not tracked';
  document.getElementById('sess2').innerHTML = (u.t0?('since '+esc(u.t0)+(u.sess_secs?' ('+fdur(u.sess_secs)+')':'')):'')+
    (u.idle_sec>120?'<span style="color:var(--run)">'+idle+'</span>':idle)+
    (u.healed?' <span style="color:var(--vio)">· healed→live transcript</span>':'');
  setV('ctx', u.ctx ? fmt(u.ctx)+' / '+fmt(u.ctx_limit) : '—');
  const bar=document.getElementById('ctxbar'); bar.style.width=Math.min(u.ctx_pct,100)+'%'; bar.className=u.ctx_pct>80?'warn':'';
  let eta='';
  if(u.series.length>5){const a=u.series[u.series.length-6],b=u.series[u.series.length-1];
    const dt=tsec(b.ts)-tsec(a.ts), dc=b.ctx-a.ctx;
    if(dt>0&&dc>0){const mins=Math.round((u.ctx_limit-u.ctx)/(dc/dt*60));
      if(mins>0&&mins<6000) eta=' · ~'+(mins>120?Math.round(mins/60)+'h':mins+'m')+' to limit';}}
  document.getElementById('ctx2').textContent = u.ctx ? (u.ctx_pct+'% · compactions '+u.session.compactions+eta) : '';
  setV('tok', fmt(u.tokens.in+u.tokens.cache_read+u.tokens.cache_write)+' / '+fmt(u.tokens.out));
  document.getElementById('tok2').textContent = 'cache hit '+u.cache_hit_pct+'% · saved ~$'+u.cache_saved.toFixed(0);
  setV('cost', u.cost_usd ? '$'+u.cost_usd.toFixed(2) : '—');
  const split = u.per_model.slice(0,3).map(m=>m.short.split(' ')[0].toLowerCase()+' $'+m.cost.toFixed(0)).join(' · ');
  document.getElementById('cost2').textContent = u.turns ? (u.turns+' turns · '+u.side+' side-sessions'+(u.per_model.length>1?' · '+split:'')) : '';
  const dl=p.cas.days_left;
  document.getElementById('cas').textContent = dl+' days';
  document.getElementById('cas').style.color = dl<=7?'var(--fail)':(dl<=14?'var(--run)':'');
  document.getElementById('cas2').textContent = p.cas.block;
  // rail — click → phase inspector
  document.getElementById('rail').innerHTML = PH.map(ph=>{
    const st=s.phases[ph[0]]||{status:'pending',detail:'',ts:'',src:''};
    const ev=(st.status!=='pending')?((st.src&&st.src!=='emit'?st.src+' · ':'')+(st.ts?st.ts.slice(0,5):'')):'';
    return '<div class="step '+st.status+'" title="'+esc(st.detail||'click for evidence')+'" onclick="inspect(\'phase\',\''+ph[0]+'\')">'+
      '<div class="sn"><span>'+ph[0]+' · '+st.status.toUpperCase()+'</span><span>'+esc(ev)+'</span></div>'+
      '<div class="sl">'+ph[1]+'</div>'+(st.detail?'<div class="se">'+esc(st.detail)+'</div>':'')+'</div>';
  }).join('');
  const ch=document.getElementById('chips');
  if(s.active.length){ch.style.display='block';
    ch.innerHTML='<span style="font-size:10px;letter-spacing:.14em;color:var(--run);font-weight:600">RUNNING AGENTS</span> '+
      s.active.map(a=>'<span class="chip" onclick="inspect(\'agent\',\''+esc(a.ts)+'\',\''+esc(a.agent)+'\')"><span class="dot"></span><b>'+esc(a.agent)+'</b>'+(a.model?' · '+esc(a.model):'')+(a.desc?' — '+esc(a.desc):'')+(elapsed(a.ts)?' · '+elapsed(a.ts):'')+'</span>').join('');}
  else ch.style.display='none';
  document.getElementById('mission').textContent = u.mission ? '» '+u.mission : '— no mission yet';
  const g={pending:[],in_progress:[],completed:[]};
  (u.todos||[]).forEach(t=>(g[t.status]||g.pending).push(t));
  document.getElementById('doing').innerHTML = g.in_progress.map(t=>'<div class="kitem doing">'+esc(t.content)+'</div>').join('')
    || (s.active.length? s.active.map(a=>'<div class="kitem doing dlgc" onclick="inspect(\'agent\',\''+esc(a.ts)+'\',\''+esc(a.agent)+'\')"><span class="dot"></span><b>'+esc(a.agent)+'</b>'+(a.desc?' — '+esc(a.desc):'')+'<span class="meta">'+elapsed(a.ts)+'</span></div>').join('')
    : '<div class="empty">no tracked task in progress — appears from the session’s task list (TaskCreate/TodoWrite)</div>');
  const freshTop = s.feed && s.feed[0] && s.feed[0].ts!==lastFeedTs && lastFeedTs!==null;
  document.getElementById('minifeed').innerHTML = (s.feed||[]).slice(0,5).map((e,i)=>feedRow(e, freshTop&&i===0)).join('')
    || '<div class="empty">dispatches, returns and phase emits stream here</div>';
  document.getElementById('alerts').innerHTML = s.alerts.length
    ? s.alerts.map(a=>'<div class="alert '+a.lvl+'">&#9888; '+esc(a.msg)+'</div>').join('')
    : '<div class="alert none">all clear</div>';
  document.getElementById('branch').textContent = p.git.branch+(p.git.ahead!=='0'?' (+'+p.git.ahead+')':'');
  const dEl=document.getElementById('dirty'); dEl.textContent=p.git.dirty?p.git.dirty+' uncommitted':'clean'; dEl.className='pv '+(p.git.dirty?'warn':'good');
  const tEl=document.getElementById('tests');
  if(u.tests){ tEl.textContent=u.tests.passed+' passed'+(u.tests.failed?' · '+u.tests.failed+' failed':'')+' · '+u.tests.ts;
    tEl.className='pv '+(u.tests.failed?'bad':'good'); } else { tEl.textContent='—'; tEl.className='pv'; }
  document.getElementById('taskline').textContent=(g.in_progress.length+g.pending.length+g.completed.length)?
    (g.in_progress.length+' doing · '+g.pending.length+' pending · '+g.completed.length+' done'):'—';
  const eEl=document.getElementById('errn'); eEl.textContent=u.errors.n||'0'; eEl.className='pv '+(u.errors.n>4?'warn':'good');
  const jEl=document.getElementById('journal'); jEl.textContent=p.journal.today?'✓':'✗ missing'; jEl.className='pv '+(p.journal.today?'good':'bad');
  const tmax=Math.max(...(u.toolhist||[]).map(x=>x[1]),1);
  document.getElementById('thist').innerHTML=(u.toolhist||[]).map(x=>'<div class="hbar"><span class="hn">'+esc(x[0])+'</span><span class="hb" style="width:'+Math.max(4,Math.round(140*x[1]/tmax))+'px"></span><span>'+x[1]+'</span></div>').join('')||'<div class="s">—</div>';
  const last=u.series[u.series.length-1]||{};
  spark('c1',u.series,'ctx','#0EA5E9'); spark('c2',u.series,'cost','#FBBF24'); spark('c3',u.series,'out','#34D399');
  document.getElementById('c1v').textContent=last.ctx?fmt(last.ctx):''; document.getElementById('c2v').textContent=last.cost?'$'+last.cost.toFixed(2):'';
  document.getElementById('c3v').textContent=last.out?fmt(last.out):'';
  // pipeline tab
  const allPend = Object.values(s.phases).every(x=>x.status==='pending');
  const rh=document.getElementById('runhint');
  if(allPend && (u.delegations.length || u.session.status==='active')){
    rh.style.display='block';
    rh.textContent='no /ship run detected in this session — '+(u.delegations.length?u.delegations.length+' delegation(s) ran on non-pipeline work (graph build, recon, docs …). ':'')+'The rail lights when shipping evidence appears: a Plan agent, implementers, gates, or an emit.';
  } else rh.style.display='none';
  document.getElementById('phasesFull').innerHTML = PH.map(ph=>{
    const st=s.phases[ph[0]]||{status:'pending',detail:'',ts:'',src:''};
    return '<div class="phase"><div class="num'+(st.status==='running'?' live':'')+'">'+ph[0]+'</div>'+
      '<div class="box '+(st.status==='running'?'run':(st.status==='fail'?'fail':''))+'" onclick="inspect(\'phase\',\''+ph[0]+'\')">'+
      '<div class="row"><span class="name">'+ph[1]+'</span><span class="st '+st.status+'">'+st.status.toUpperCase()+'</span>'+
      (st.src&&st.status!=='pending'?'<span class="src">'+st.src+'</span>':'')+'<span class="ts">'+(st.ts||'')+'</span></div>'+
      '<div class="who">'+ph[2]+'</div>'+(st.detail?'<div class="detail">'+esc(st.detail)+'</div>':'')+'</div></div>';
  }).join('');
  document.getElementById('evfeed').innerHTML = (s.feed||[]).map((e,i)=>feedRow(e, freshTop&&i===0)).join('')
    || '<div class="empty">no activity yet — dispatches, returns and emits land here (hooks ∪ transcript)</div>';
  if(s.feed && s.feed[0]) lastFeedTs=s.feed[0].ts;
  document.getElementById('evlog').textContent = s.event_tail.map(e=>JSON.stringify(e)).join('\n') || '—';
  const gh=s.gh;
  document.getElementById('ghpanel').innerHTML = !gh ? '<div class="empty">gh unavailable (not installed / not authed) — phase 06 falls back to command sensing</div>'
    : ((gh.prs.length? gh.prs.map(pr=>'<div class="cirow"><b>#'+pr.n+'</b><span>'+esc(pr.br)+'</span>'+
        '<span class="ok">'+pr.ok+'✓</span>'+(pr.fail?'<span class="bad">'+pr.fail+'✗</span>':'')+(pr.pend?'<span class="pend">'+pr.pend+'◌</span>':'')+
        '<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+esc(pr.t)+'</span></div>').join('') : '<div class="s">no open PRs</div>')
      +'<div class="k" style="margin-top:10px">recent workflow runs</div>'
      +(gh.runs.length? gh.runs.map(r=>'<div class="cirow"><span>'+esc(r.at)+'</span><span class="'+(r.st==='success'?'ok':(r.st==='failure'?'bad':'pend'))+'">'+esc(r.st)+'</span><span>'+esc(r.wf)+'</span><span>'+esc(r.br)+'</span></div>').join(''):'<div class="s">none</div>'));
  document.getElementById('gh8').innerHTML=(u.gatehist||[]).slice(0,5).map(g2=>'<div class="cirow"><span>'+esc(g2.ts)+'</span><span class="'+(g2.ok?'ok':'bad')+'">'+esc(g2.kind)+'</span><span>'+(g2.passed!=null?g2.passed+' passed'+(g2.failed?' · '+g2.failed+' failed':''):(g2.ok?'clean':'errors'))+'</span></div>').join('')||'<div class="s">no gate runs observed yet</div>';
  // agents tab
  document.getElementById('mtb').innerHTML = u.per_model.map(m=>'<tr class="clk" onclick="inspect(\'model\',\''+esc(m.model)+'\')"><td>'+esc(m.short)+' <span style="color:var(--faint)">'+esc(m.model)+'</span></td><td>'+fmt(m.in)+'</td><td>'+fmt(m.cr)+' / '+fmt(m.cw)+'</td><td>'+fmt(m.out)+'</td><td>$'+m.cost.toFixed(2)+'</td></tr>').join('') || '<tr><td colspan="5">no usage yet</td></tr>';
  document.getElementById('sessmeta').textContent='context = latest main-turn input incl. cache · subagent usage read from sidechain transcripts · prices editable in shipboard.py';
  document.getElementById('ss1').innerHTML=esc(u.session.status)+(u.idle_sec>120?' <span style="color:var(--run)">· idle '+fdur(u.idle_sec)+'</span>':' · live');
  document.getElementById('ss2').textContent=(u.t0||'—')+(u.sess_secs?' · '+fdur(u.sess_secs):'');
  document.getElementById('ss4').textContent=u.turns+' / '+u.prompts+' / '+u.tools;
  document.getElementById('ss5').textContent=u.session.compactions;
  document.getElementById('ss6').textContent=u.cache_hit_pct+'% · ~$'+u.cache_saved.toFixed(0)+' saved';
  document.getElementById('ss7').textContent=u.side+' · '+u.side_matched+' matched';
  document.getElementById('ss8').textContent='$'+u.cost_main.toFixed(2)+' / $'+u.cost_side.toFixed(2);
  document.getElementById('ss9').textContent=(u.sess_secs&&u.cost_usd)?('$'+(u.cost_usd/(u.sess_secs/3600)).toFixed(0)+'/h · '+fmt(Math.round(u.tokens.out/(Math.max(u.sess_secs,60)/60)))+' out-tok/min'):'—';
  timeline(u.delegations);
  document.getElementById('atb').innerHTML = u.delegations.map(d=>'<tr class="clk" onclick="inspect(\'agent\',\''+esc(d.ts)+'\',\''+esc(d.agent)+'\')"><td>'+esc(d.ts)+'</td><td>'+esc(d.agent)+'</td><td>'+esc(d.model||'')+'</td><td>'+esc(d.desc)+'</td>'+
      '<td>'+(d.live?elapsed(d.ts):(d.dur_s!=null?fdur(d.dur_s):''))+'</td>'+
      '<td>'+(d.tin!=null?fmt(d.tin)+' / '+fmt(d.tout):'—')+'</td>'+
      '<td>'+(d.cost!=null?'$'+d.cost.toFixed(2):'—')+'</td>'+
      '<td>'+(d.live?'<span style="color:var(--run)">⟲ live</span>':(d.done?'<span style="color:var(--ok)">✓ done'+(d.has_report?' ▸':'')+'</span>':'?'))+'</td></tr>').join('')
    || '<tr><td colspan="8">no delegations yet — dispatches appear here with model, duration and cost</td></tr>';
  // project tab
  document.getElementById('blockNow').textContent=p.cas.block;
  document.getElementById('blocks').innerHTML=p.cas.blocks.map(b=>'<div class="blk '+b.state+'"><b>'+esc(b.label)+'</b>'+b.range+
    (b.state==='now'?'<div class="gauge"><i style="width:'+b.pct+'%"></i></div>':'')+'</div>').join('');
  document.getElementById('commits').innerHTML=p.git.commits.map(c=>{
    const h=(c.split(' · ')[0]||'').trim();
    return '<div class="lst clk" onclick="inspect(\'commit\',\''+esc(h)+'\')">'+esc(c)+'</div>';}).join('');
  document.getElementById('jcount').textContent='· '+p.journal.entries+' entries total';
  document.getElementById('jprev').innerHTML=p.journal.today?mdlite(p.journal.preview.join('\n')):'<span style="color:var(--fail)">no entry yet today — 2 minutes, 12 points.</span>';
  document.getElementById('ev1').textContent=u.tests?(u.tests.passed+' passed'+(u.tests.failed?' · '+u.tests.failed+' failed':'')+' · '+u.tests.ts):'no gate run seen';
  document.getElementById('ev1').className='pv '+(u.tests?(u.tests.failed?'bad':'good'):'');
  document.getElementById('ev2').textContent=p.journal.entries;
  document.getElementById('ev3').textContent=p.vault.fazit;
  document.getElementById('ev4').textContent=p.vault.learnings;
  const F=p.flags;
  document.getElementById('flags').innerHTML=[['boundary test',F.boundary],['compose',F.compose],['helm',F.helm],['ci.yml',F.ci],['mkdocs',F.docs]]
    .map(x=>'<span class="flag '+(x[1]?'on':'off')+'">'+(x[1]?'✓':'✗')+' '+esc(x[0])+'</span>').join('');
  document.getElementById('ciruns').innerHTML=(gh&&gh.runs.length)?gh.runs.map(r=>'<div class="cirow"><span>'+esc(r.at)+'</span><span class="'+(r.st==='success'?'ok':(r.st==='failure'?'bad':'pend'))+'">'+esc(r.st)+'</span><span>'+esc(r.wf)+'</span><span>'+esc(r.br)+'</span></div>').join(''):'<div class="s">'+(gh?'none yet':'gh unavailable')+'</div>';
  document.getElementById('svc').innerHTML=(p.services||[]).map(x=>'<div class="prow" style="margin:4px 0"><span class="pk">'+esc(x.n)+'</span><span class="pv">'+x.src+' / <span style="color:var(--ok)">'+x.tests+'</span></span></div>').join('')||'<div class="s">no services yet</div>';
  document.getElementById('adrn2').textContent=p.adrs.count;
  document.getElementById('adrlist').innerHTML=p.adrs.list.map(a=>{
    const sc=a.s==='superseded'?'sup':(a.s==='accepted'?'acc':(a.s?'oth':''));
    return '<div class="lst clk'+(sc==='sup'?' sup':'')+'" onclick="inspect(\'adr\',\''+esc(a.f)+'\')">'+(a.s?'<span class="adrb '+sc+'">'+esc(a.s.slice(0,10))+'</span>':'· ')+esc(a.t)+'</div>';
  }).join('')||'<div class="lst">none yet</div>';
}
tick(); setInterval(tick, 2000);
</script></body></html>"""

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/state":
            body = json.dumps(state()).encode()
            ct = "application/json"
        elif url.path == "/detail":
            try:
                body = json.dumps(detail(parse_qs(url.query))).encode()
            except Exception as ex:
                body = json.dumps({"err": f"detail failed: {ex}"}).encode()
            ct = "application/json"
        elif url.path == "/vaultgraph":
            body = json.dumps(vault_graph()).encode()
            ct = "application/json"
        elif url.path == "/graphify":
            gf = ROOT / "graphify-out" / "graph.html"
            if gf.exists():
                body = gf.read_bytes()
            else:
                body = (b"<body style='background:#06263B;color:#7DD3FC;font-family:monospace;"
                        b"padding:40px'>graphify-out/graph.html not found &mdash; run /graphify . "
                        b"in a Claude session once, then reload this tab.</body>")
            ct = "text/html; charset=utf-8"
        else:
            body = HTML.replace("%PHASES%", json.dumps(PHASES)).encode()
            ct = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_POST(self):
        if self.path == "/reset":
            try:
                LOG.unlink(missing_ok=True)
            except OSError:
                if LOG.exists():
                    LOG.write_text("", encoding="utf-8")
            _T["sensed"] = {}
            self.send_response(200); self.send_header("Content-Length", "2"); self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404); self.end_headers()

def demo():
    SB.mkdir(exist_ok=True)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    rows = [
        {"kind":"phase","phase":"01","status":"pass","detail":"plan approved by Erhan (3 tasks)","ts":now},
        {"kind":"phase","phase":"02","status":"pass","detail":"2 implementers · 14 tests added","ts":now},
        {"kind":"phase","phase":"03","status":"pass","detail":"ruff clean · 87 passed","ts":now},
        {"kind":"phase","phase":"04","status":"running","detail":"verifier + determinism-auditor in flight","ts":now},
        {"kind":"agent","phase":None,"status":"active","detail":"diff-vs-plan check","agent":"verifier","model":"Fable 5","ts":now},
        {"kind":"agent","phase":None,"status":"active","detail":"freeze-line audit","agent":"determinism-auditor","model":"Sonnet 4.6","ts":now},
    ]
    LOG.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    print(f"demo run seeded → {LOG}")

if __name__ == "__main__":
    if "--reset" in sys.argv:
        try:
            LOG.unlink(missing_ok=True)
        except OSError:
            if LOG.exists():
                LOG.write_text("", encoding="utf-8")
        print("event log cleared"); sys.exit(0)
    if "--demo" in sys.argv:
        demo()
    print(f"shipboard v8 → http://localhost:{PORT}")
    HTTPServer(("127.0.0.1", PORT), H).serve_forever()
