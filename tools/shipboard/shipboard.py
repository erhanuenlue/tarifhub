#!/usr/bin/env python3
"""Shipboard — one-file live dashboard for the /ship pipeline.

Usage:
  python3 tools/shipboard/shipboard.py            # serve http://localhost:8787
  python3 tools/shipboard/shipboard.py --demo     # seed a demo run, then serve
  python3 tools/shipboard/shipboard.py --reset    # clear the event log

stdlib only — runs before any venv exists. Events come from tools/shipboard/emit.sh
(phases, called by the /ship skill) and .claude/hooks/shipboard_emit.sh (agents, automatic).
"""
import json, sys, time, pathlib
from http.server import HTTPServer, BaseHTTPRequestHandler

ROOT = pathlib.Path(__file__).resolve().parents[2]
LOG = ROOT / ".shipboard" / "events.jsonl"
PORT = 8787

PHASES = [
    ("01", "Plan (approval gate)", "inline · Fable 5"),
    ("02", "Implement (TDD)", "implementer · Opus 4.8"),
    ("03", "Local gates", "inline · Fable 5"),
    ("04", "Reviews", "verifier · Fable 5 / determinism · Sonnet / security · Opus / codex · Haiku"),
    ("05", "Fix cycle", "orchestrated · Fable 5"),
    ("06", "PR + CI", "inline · Fable 5"),
    ("07", "Runtime E2E + logs", "e2e-tester · Sonnet 4.6"),
    ("08", "Full report", "inline · Fable 5"),
    ("09", "Merge (confirmation gate)", "Erhan"),
]

def read_events():
    if not LOG.exists():
        return []
    out = []
    for line in LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out

def state():
    ev = read_events()
    phases = {p[0]: {"status": "pending", "detail": "", "ts": ""} for p in PHASES}
    agents, started = [], ""
    for e in ev:
        if e.get("kind") == "phase" and e.get("phase") in phases:
            phases[e["phase"]] = {"status": e.get("status", "?"),
                                  "detail": e.get("detail", ""), "ts": e.get("ts", "")}
            if e["phase"] == "01" and not started:
                started = e.get("ts", "")
        elif e.get("kind") == "agent":
            agents.append(e)
    active = {}
    for a in agents:
        if a.get("status") == "active":
            active[a.get("agent")] = a
        elif a.get("status") == "done":
            active.pop(a.get("agent"), None)
    return {"phases": phases, "active": list(active.values()),
            "recent": agents[-8:], "started": started,
            "updated": time.strftime("%H:%M:%S"), "events": len(ev)}

HTML = """<!doctype html><html><head><meta charset="utf-8"><title>shipboard — tarifhub</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
:root{--navy:#0C4A6E;--deep:#06263B;--sky:#0EA5E9;--cyan:#22D3EE;--paper:rgba(255,255,255,.92);
--dim:rgba(186,230,253,.75);--faint:rgba(186,230,253,.4);--card:rgba(255,255,255,.05);
--edge:rgba(125,211,252,.18);--ok:#34D399;--run:#FBBF24;--fail:#F87171}
body{margin:0;padding:28px 34px;background:radial-gradient(1100px 600px at 75% -10%,#0E5A85 0%,var(--navy) 40%,var(--deep) 100%);
min-height:100vh;font-family:Inter,system-ui,sans-serif;color:var(--paper)}
h1{font-size:30px;font-weight:800;margin:0}
h1 .slash{color:var(--sky)} h1 small{font-weight:400;font-size:14px;color:var(--faint)}
.meta{font-family:'JetBrains Mono';font-size:12px;color:var(--dim);margin:6px 0 22px}
.badge{display:inline-block;font-family:'JetBrains Mono';font-size:11px;font-weight:600;padding:2px 10px;
border-radius:99px;border:1px solid;vertical-align:middle;margin-left:10px}
.badge.run{color:var(--run);border-color:var(--run)} .badge.ok{color:var(--ok);border-color:var(--ok)}
.badge.fail{color:var(--fail);border-color:var(--fail)} .badge.idle{color:var(--faint);border-color:var(--faint)}
.agents{background:rgba(251,191,36,.06);border:1px solid rgba(251,191,36,.25);border-radius:12px;
padding:10px 16px;margin-bottom:20px;font-size:13px}
.agents b{color:var(--run);font-size:11px;letter-spacing:.15em}
.chip{display:inline-block;font-family:'JetBrains Mono';font-size:11.5px;padding:3px 11px;margin:2px 4px;
border-radius:99px;background:var(--card);border:1px solid var(--edge);color:var(--dim)}
.chip b{color:#fff;font-weight:600}
.phase{display:flex;gap:18px;margin:10px 0;align-items:flex-start}
.num{font-family:'JetBrains Mono';font-size:22px;font-weight:600;color:var(--faint);width:44px;padding-top:14px}
.num.live{color:var(--sky)}
.box{flex:1;background:var(--card);border:1px solid var(--edge);border-radius:14px;padding:13px 18px}
.box.run{border-color:rgba(251,191,36,.5)} .box.fail{border-color:rgba(248,113,113,.5)}
.row{display:flex;align-items:center;gap:12px}
.name{font-weight:600;font-size:16px}
.st{font-family:'JetBrains Mono';font-size:10.5px;font-weight:600;letter-spacing:.1em;padding:2px 9px;border-radius:4px}
.st.pending{background:rgba(255,255,255,.07);color:var(--faint)}
.st.running{background:rgba(251,191,36,.15);color:var(--run);border:1px solid rgba(251,191,36,.4)}
.st.pass{background:rgba(52,211,153,.15);color:var(--ok)} .st.fail{background:rgba(248,113,113,.15);color:var(--fail)}
.st.skip{background:rgba(255,255,255,.07);color:var(--faint);text-decoration:line-through}
.ts{margin-left:auto;font-family:'JetBrains Mono';font-size:11px;color:var(--faint)}
.who{font-size:12px;color:var(--dim);margin-top:6px;font-family:'JetBrains Mono'}
.detail{font-size:12.5px;color:var(--dim);margin-top:4px}
</style></head><body>
<h1><span class="slash">/ship</span> shipboard <small id="upd"></small><span id="badge" class="badge idle">IDLE</span></h1>
<div class="meta" id="meta">tarifhub · multi-model pipeline · Fable 5 orchestrates · Opus implements · Sonnet verifies</div>
<div class="agents" id="agents" style="display:none"><b>&#9889; ACTIVE AGENTS</b> <span id="agentchips"></span></div>
<div id="phases"></div>
<script>
const PH = %PHASES%;
async function tick(){
  let s; try { s = await (await fetch('/state')).json(); } catch(e){ return; }
  document.getElementById('upd').textContent = 'updated ' + s.updated + ' · ' + s.events + ' events';
  const sts = Object.values(s.phases).map(p=>p.status);
  const badge = document.getElementById('badge');
  if (sts.includes('fail')) { badge.textContent='ATTENTION'; badge.className='badge fail'; }
  else if (sts.includes('running')) { badge.textContent='RUNNING'; badge.className='badge run'; }
  else if (s.phases['09'] && s.phases['09'].status==='pass') { badge.textContent='SHIPPED'; badge.className='badge ok'; }
  else { badge.textContent='IDLE'; badge.className='badge idle'; }
  const ag = document.getElementById('agents');
  if (s.active.length){ ag.style.display='block';
    document.getElementById('agentchips').innerHTML = s.active.map(a=>'<span class="chip">&#9679; <b>'+a.agent+'</b> · '+(a.model||'')+'</span>').join('');
  } else ag.style.display='none';
  document.getElementById('phases').innerHTML = PH.map(p=>{
    const st = s.phases[p[0]] || {status:'pending',detail:'',ts:''};
    return '<div class="phase"><div class="num'+(st.status==='running'?' live':'')+'">'+p[0]+'</div>'+
      '<div class="box '+(st.status==='running'?'run':(st.status==='fail'?'fail':''))+'">'+
      '<div class="row"><span class="name">'+p[1]+'</span><span class="st '+st.status+'">'+st.status.toUpperCase()+'</span>'+
      '<span class="ts">'+(st.ts||'')+'</span></div>'+
      '<div class="who">'+p[2]+'</div>'+
      (st.detail?'<div class="detail">'+st.detail+'</div>':'')+'</div></div>';
  }).join('');
}
tick(); setInterval(tick, 2000);
</script></body></html>"""

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path == "/state":
            body = json.dumps(state()).encode()
            ct = "application/json"
        else:
            body = HTML.replace("%PHASES%", json.dumps(PHASES)).encode()
            ct = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

def demo():
    LOG.parent.mkdir(exist_ok=True)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    rows = [
        {"kind":"phase","phase":"01","status":"pass","detail":"plan approved by Erhan (3 tasks)","ts":now},
        {"kind":"phase","phase":"02","status":"pass","detail":"2 implementers · 14 tests added","ts":now},
        {"kind":"phase","phase":"03","status":"pass","detail":"ruff clean · 87 passed","ts":now},
        {"kind":"phase","phase":"04","status":"running","detail":"verifier + determinism-auditor in flight","ts":now},
        {"kind":"agent","phase":None,"status":"active","detail":"","agent":"verifier","model":"Fable 5","ts":now},
        {"kind":"agent","phase":None,"status":"active","detail":"","agent":"determinism-auditor","model":"Sonnet 4.6","ts":now},
    ]
    LOG.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    print(f"demo run seeded → {LOG}")

if __name__ == "__main__":
    if "--reset" in sys.argv:
        try:
            LOG.unlink(missing_ok=True)
        except OSError:
            if LOG.exists():
                LOG.write_text("", encoding="utf-8")  # truncate when the FS forbids delete
        print("event log cleared"); sys.exit(0)
    if "--demo" in sys.argv:
        demo()
    print(f"shipboard → http://localhost:{PORT}   (events: {LOG})")
    HTTPServer(("127.0.0.1", PORT), H).serve_forever()
