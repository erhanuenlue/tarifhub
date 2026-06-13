#!/usr/bin/env python3
"""Telegram bridge for the approval queue. Stdlib only (urllib), no pip deps.

One long-running daemon that keeps Telegram and the dashboard in sync through one shared
queue under .shipboard/approvals/. It does three things in a loop:
  1. watches pending/   -> sends a message with inline Approve/Deny buttons
  2. polls getUpdates   -> a button tap writes decided/<id>.json (via="telegram")
  3. watches decided/   -> if the dashboard decided first, edits the Telegram message to say so

The decision file is the single source of truth. First writer wins; the other surface reflects
it on its next poll. Run alongside the board:
    TG_BOT_TOKEN=... TG_CHAT_ID=... nohup python3 tools/approval_telegram.py >> .shipboard/tg.log 2>&1 &

Security: hard allowlist on TG_CHAT_ID (every other chat is ignored); token comes from the env
(.env), never the repo; it can only ever write a decided/ file, nothing else.
"""
import json, os, time, urllib.parse, urllib.request
from pathlib import Path

BOT = os.environ.get("TG_BOT_TOKEN", "")
CHAT = str(os.environ.get("TG_CHAT_ID", ""))
ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")).resolve()
Q = ROOT / ".shipboard" / "approvals"
API = f"https://api.telegram.org/bot{BOT}"


def tg(method, **params):
    data = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}).encode()
    try:
        with urllib.request.urlopen(f"{API}/{method}", data=data, timeout=30) as r:
            return json.load(r)
    except Exception:
        return {}


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def main():
    if not BOT or not CHAT:
        print("approval_telegram: TG_BOT_TOKEN / TG_CHAT_ID not set, exiting")
        return
    (Q / "pending").mkdir(parents=True, exist_ok=True)
    (Q / "decided").mkdir(parents=True, exist_ok=True)
    msg_id = {}          # request id -> telegram message_id
    edited = set()       # ids already reflected back to telegram
    offset = None
    print(f"approval_telegram: watching {Q}")
    while True:
        # 1) announce new pending requests
        for p in sorted((Q / "pending").glob("*.json")):
            rid = p.stem
            if rid in msg_id:
                continue
            try:
                r = json.loads(p.read_text())
            except Exception:
                continue
            kb = {"inline_keyboard": [[
                {"text": "✅ Approve", "callback_data": f"a:{rid}"},
                {"text": "⛔ Deny", "callback_data": f"d:{rid}"}]]}
            res = tg("sendMessage", chat_id=CHAT,
                     text=f"Approval needed\nrisk: {r.get('risk')}\n{r.get('summary','')}",
                     reply_markup=json.dumps(kb))
            mid = (res.get("result") or {}).get("message_id")
            if mid:
                msg_id[rid] = mid
        # 2) consume button taps
        upd = tg("getUpdates", offset=offset, timeout=10)
        for u in upd.get("result", []):
            offset = u["update_id"] + 1
            cb = u.get("callback_query")
            if not cb:
                continue
            if str(cb.get("message", {}).get("chat", {}).get("id")) != CHAT:
                tg("answerCallbackQuery", callback_query_id=cb["id"], text="not authorized")
                continue
            try:
                act, rid = cb["data"].split(":", 1)
            except ValueError:
                continue
            dec = "allow" if act == "a" else "deny"
            dpath = Q / "decided" / f"{rid}.json"
            if not dpath.exists():     # first writer wins
                dpath.write_text(json.dumps({"id": rid, "decision": dec, "via": "telegram",
                                             "by": "erhan", "ts": now_iso()}))
            tg("answerCallbackQuery", callback_query_id=cb["id"], text=f"{dec} recorded")
        # 3) reflect dashboard-side decisions back into Telegram
        for d in (Q / "decided").glob("*.json"):
            rid = d.stem
            if rid in msg_id and rid not in edited:
                try:
                    rec = json.loads(d.read_text())
                except Exception:
                    continue
                if rec.get("via") != "telegram":
                    tg("editMessageText", chat_id=CHAT, message_id=msg_id[rid],
                       text=f"resolved via {rec.get('via')}: {rec.get('decision')}")
                edited.add(rid)
        time.sleep(1)


if __name__ == "__main__":
    main()
