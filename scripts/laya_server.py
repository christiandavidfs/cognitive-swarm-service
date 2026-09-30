#!/usr/bin/env python3
"""Local LAYA sidecar — wraps the open-weights checkpoint in the SystemOne
shape our judge seam already speaks (POST /v1/systemone).

This is a POC BRIDGE: the exact inference call into the `convaiinnovations/laya`
checkpoint must be verified against the real HF artifact during Gate A (the
vendor publishes transformers tooling; community runtimes exist for ONNX/MLX).
The judge contract it serves is stable — swap the internals, keep the shape.

Requires: pip install torch transformers  (NOT in requirements — optional).
Run:  LAYA_MODEL=convaiinnovations/laya python scripts/laya_server.py
Env:  LAYA_SERVER_HOST (default 127.0.0.1)  LAYA_SERVER_PORT (default 8021)
"""
from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL_ID = os.getenv("LAYA_MODEL", "convaiinnovations/laya")


def _load_model():
    try:
        import torch  # noqa: F401
        from transformers import AutoModel, AutoTokenizer
    except ImportError as e:
        raise SystemExit(
            "LAYA sidecar needs optional deps: pip install torch transformers "
            f"(missing: {e}). The service itself runs without this sidecar."
        )
    tok = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModel.from_pretrained(MODEL_ID)
    model.eval()
    return tok, model


_tok_model = None  # lazy singleton


def _evaluate(state: str, questions: dict) -> dict:
    """TODO(Gate A): replace with the checkpoint's real typed-decision head call.
    Current placeholder returns a flat distribution so the contract and the
    bench harness can be exercised end-to-end before model wiring lands."""
    global _tok_model
    if _tok_model is None:
        _tok_model = _load_model()
    answers = {}
    for name, q in (questions or {}).items():
        opts = list((q.get("criteria") or {}).keys()) or ["unknown"]
        answers[name] = {
            "type": q.get("type", "choice"),
            "choice": None,
            "probabilities": {o: 1.0 / len(opts) for o in opts},
            "confidence": 0.0,
            "escalate": False,
        }
    return answers


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/v1/systemone":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        try:
            answers = _evaluate(body.get("state", ""), body.get("questions", {}))
            payload = json.dumps({"answers": answers}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except Exception as e:  # noqa: BLE001 — sidecar must answer, not crash
            payload = json.dumps({"error": str(e)}).encode()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    def log_message(self, fmt, *args):  # quieter default
        if os.getenv("LAYA_SERVER_VERBOSE"):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main():
    host = os.getenv("LAYA_SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("LAYA_SERVER_PORT", "8021"))
    print(f"LAYA sidecar on http://{host}:{port}  model={MODEL_ID}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
