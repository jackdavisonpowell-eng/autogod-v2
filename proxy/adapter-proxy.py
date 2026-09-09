#!/usr/bin/env python3
"""Adapter proxy: folds trailing system-role messages (Qwen template rejects
them) into the top-level system block, forwards to the local brain, streams
the response back incrementally, and logs one JSON line per request.

Config via env:
  AUTOGOD_UPSTREAM    default http://127.0.0.1:11466
  AUTOGOD_PROXY_PORT  default 11499
  AUTOGOD_PROXY_LOG   default ~/autogod-v2/state/proxy.log
"""
import http.server, json, os, re, socketserver, sys, time, urllib.request, urllib.error

UP = os.environ.get("AUTOGOD_UPSTREAM", "http://127.0.0.1:11466")
PORT = int(os.environ.get("AUTOGOD_PROXY_PORT", "11499"))
LOG = os.path.expanduser(os.environ.get("AUTOGOD_PROXY_LOG", "~/autogod-v2/state/proxy.log"))
# Per-request cap on the brain's reasoning (llama-server: reasoning_budget_tokens).
# Uncapped, the 27B thinks for 10 minutes on a "pick an idea" turn and Claude Code's
# client times out with nothing (2026-09-09). 0 = don't inject.
THINK_BUDGET = int(os.environ.get("AUTOGOD_REASONING_BUDGET", "3072"))
# Hard wall-clock cap per turn: a turn that streams for longer than this is cut off
# (the 27B otherwise thinks for 20+ minutes and the harness budget kills the whole pass).
TURN_MAX = int(os.environ.get("AUTOGOD_TURN_MAX_SECS", "900"))
THINK_RE = re.compile(rb'"thinking"\s*:\s*"((?:[^"\\]|\\.)*)"')
os.makedirs(os.path.dirname(LOG), exist_ok=True)

def fold_system(d):
    """Move any non-leading system-role message into d['system']; return folded count."""
    msgs = d.get("messages", []); extra = []; keep = []
    for m in msgs:
        if m.get("role") == "system":
            c = m.get("content")
            extra.append(c if isinstance(c, str) else " ".join(x.get("text", "") for x in c if isinstance(x, dict)))
        else:
            keep.append(m)
    if extra:
        sysm = d.get("system") or []
        if isinstance(sysm, str): sysm = [{"type": "text", "text": sysm}]
        d["system"] = sysm + [{"type": "text", "text": t} for t in extra]
        d["messages"] = keep
    return len(extra)

class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass

    def do_POST(self):
        n = int(self.headers.get("content-length", 0)); body = self.rfile.read(n)
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "path": self.path}
        try:
            d = json.loads(body)
            rec["roles"] = [m.get("role") for m in d.get("messages", [])]
            rec["tools"] = len(d.get("tools", []))
            rec["stream"] = bool(d.get("stream"))
            rec["folded_system"] = fold_system(d)
            # llama-server re-prefilled all 32k tokens every turn on this endpoint
            # (n_prompt_tokens_cache = 0, 2026-09-09); ask for the prompt cache explicitly.
            d.setdefault("cache_prompt", True)
            th = d.get("thinking")
            if isinstance(th, dict):
                rec["thinking_param"] = th
            if THINK_BUDGET:
                d["reasoning_budget_tokens"] = THINK_BUDGET
                if isinstance(th, dict) and th.get("type") == "enabled":
                    th["budget_tokens"] = min(int(th.get("budget_tokens") or THINK_BUDGET), THINK_BUDGET)
                rec["think_budget"] = THINK_BUDGET
            body = json.dumps(d).encode()
        except Exception as e:
            rec["parse_error"] = str(e)

        fwd_headers = {k: v for k, v in self.headers.items()
                       if k.lower() in ("content-type", "anthropic-version", "accept")}
        req = urllib.request.Request(UP + self.path, data=body, method="POST", headers=fwd_headers)
        t0 = time.time()
        in_tok = out_tok = None
        think_chars = 0
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                st = r.status; hdrs = r.headers
                is_sse = "text/event-stream" in (hdrs.get("content-type") or "")
                self.send_response(st)
                for k in ("content-type",):
                    if hdrs.get(k): self.send_header(k, hdrs.get(k))
                if is_sse:
                    self.send_header("cache-control", "no-cache")
                self.send_header("transfer-encoding", "chunked")
                self.end_headers()
                for chunk in iter(lambda: r.read(4096), b""):
                    if time.time() - t0 > TURN_MAX:
                        rec["turn_cap"] = TURN_MAX
                        break
                    if is_sse:
                        in_tok, out_tok = parse_usage(chunk, in_tok, out_tok)
                        for m in THINK_RE.finditer(chunk): think_chars += len(m.group(1))
                    self.wfile.write(("%x\r\n" % len(chunk)).encode() + chunk + b"\r\n")
                self.wfile.write(b"0\r\n\r\n")
        except urllib.error.HTTPError as e:
            st = e.code; data = e.read()
            rec["err"] = data[:200].decode(errors="ignore")
            self.send_response(st)
            self.send_header("content-length", str(len(data))); self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            st = 502; rec["err"] = str(e)[:200]
            self.send_response(st); self.send_header("content-length", "0"); self.end_headers()
        rec["status"] = st; rec["secs"] = round(time.time() - t0, 1)
        if in_tok is not None: rec["input_tokens"] = in_tok
        if out_tok is not None: rec["output_tokens"] = out_tok
        if think_chars: rec["thinking_chars"] = think_chars
        with open(LOG, "a") as f: f.write(json.dumps(rec) + "\n")

USAGE_RE = re.compile(rb'"usage"\s*:\s*(\{[^}]*\})')

def parse_usage(chunk, in_tok, out_tok):
    for m in USAGE_RE.finditer(chunk):
        try:
            u = json.loads(m.group(1))
        except Exception:
            continue
        if "input_tokens" in u: in_tok = u["input_tokens"]
        if "output_tokens" in u: out_tok = u["output_tokens"]
    return in_tok, out_tok

if __name__ == "__main__":
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    class Srv(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
    Srv(("127.0.0.1", PORT), H).serve_forever()
