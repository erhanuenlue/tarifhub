# ADR-021: Cockpit control-plane security model

*Status: Proposed · Date: 2026-06-14 · Decider: Erhan (+ AI-assisted design, security-reviewed)*

## Context
The cockpit's POST endpoints authorize real, hard-to-reverse actions. `/approve` and `/deny` decide the approval gate that fronts merge-to-main, publish and destructive-git (`.claude/hooks/approval_gate.sh`); `/reset` wipes the event rail. Today these POSTs have no Origin, Host or token check (`shipboard.py` `_decide` and `do_POST`). Any web page the operator visits can issue a cross-origin POST: a "simple request" (for example `Content-Type: text/plain`) is sent without a preflight, and the side effect lands even though the response is unreadable to the attacker. A DNS-rebinding attack can additionally make `127.0.0.1` appear same-origin and read responses to enumerate pending approval ids. The existing `rid` format and existence validation stop id forgery but neither of these vectors.

## Decision
We protect every state-changing endpoint on the loopback service with a layered, stdlib-only model:
1. **Per-session bearer token (the mandatory authorizer).** `secrets.token_urlsafe(32)`, minted on each server start, written to `.shipboard/cockpit.token` mode `0600`, delivered to the same-origin page, and required on every POST as a custom header `X-Cockpit-Token`. A custom header forces a CORS preflight cross-origin, which we refuse (no `Access-Control-Allow-Headers`). A POST with a wrong or missing token is rejected `401`, full stop, regardless of Origin.
2. **Host-header allowlist (defeats DNS-rebinding).** Exact match against `{127.0.0.1:PORT, localhost:PORT, [::1]:PORT}`; a missing Host on a state-changing request is denied. A rebound request carries the attacker's domain in Host and is rejected.
3. **Origin/Referer check (defense in depth).** Reject any cross-origin Origin. Absent Origin is never an independent allow path: the token is still required.

`/reset` is in the protected set. We bind `127.0.0.1` only. A Unix-domain-socket control channel is recorded as a future opt-in for same-host isolation, where the real security property is `SO_PEERCRED` peer-uid checking, not the socket file mode.

**Explicit trust boundary.** This model defends against a malicious web page and DNS-rebinding. It does not, and a localhost token cannot, defend against a malicious same-UID local process, which already runs arbitrary code and can read the `0600` token. That isolation is out of scope and is only achievable with `SO_PEERCRED` on a Unix socket or a human-held signing key.

**Control-plane endpoints are a higher risk class than approvals.** `start` and `resume` launch `loop.sh`, which runs `claude -p --permission-mode bypassPermissions --max-turns 400`: unbounded autonomous execution, strictly more dangerous than approving one already-gated action. So the loop-control endpoints (a) form their own risk class that requires an explicit, separate confirmation, not the single click that decides an approval; (b) launch the loop in a non-bypass permission mode, or with `APPROVALS_ON=1` forced so every sensitive action inside the run is re-gated through this same approval surface; and (c) emit a `control.action` audit event per action (who, what, `run_id`, mode). In the threat model, authorizing a control-start outranks deciding a single approval, and is gated accordingly.

**Exposure ranking (what is actually reachable, and when).** `/reset` and the control plane are the durable exposure: both are always live, `/reset` destroys rail state, and a control-start launches the loop. `/approve` and `/deny` are dormant while `APPROVALS_ON` is unset (the gate no-ops and never writes a pending request), so they matter only when human-in-the-loop is enabled. All endpoints carry the same triad regardless; the always-live pair is the priority to defend, and the d2 control plane inherits this section's separate-confirmation and non-bypass requirements.

## Alternatives weighed
- **Origin check alone**: a non-browser client or a buggy Origin-parsing path can bypass it; insufficient as the sole control, which is why the token is mandatory and Origin is only defense in depth.
- **Unix socket only (no browser)**: strongest local isolation but removes the browser UI or needs a proxy; kept as an opt-in, not the default.
- **A long-lived static token in a config file**: risks a stale token authorizing a later session and, in a repo that goes public in Block 3, a committed secret; per-start regeneration in a gitignored `0600` file avoids both.

## Consequences
- (+) Closes the CSRF and DNS-rebinding holes on actions that authorize destructive git, with zero new dependencies.
- (+) The approval inbox can become a first-class UI surface without widening the attack surface.
- (–) The SSE read stream emits approval ids and `EventSource` cannot set headers, so the read plane is gated by a `SameSite=Strict` cookie set on first GET (or a loopback `?token`), and `approval_id` is treated as non-secret with the token as the sole authorizer. Any event-derived string rendered into the page is HTML-escaped so the token cannot be exfiltrated through a crafted commit message or PR title.
- (–) A late dashboard decision after the hook's roughly 9-minute timeout must not mint a phantom allow. The gate writes a terminal `timeout` decision atomically (same `os.link` first-writer-wins discipline) before denying, so a late POST returns the timeout decision instead of an allow nobody is waiting on. Revisit trigger: any exposure beyond loopback makes this model insufficient and requires real authentication.

*Lineage: new; hardens the approval bridge introduced in `prompts/12_approval_bridge.md`. Cross-reference ADR-019, ADR-020.*
