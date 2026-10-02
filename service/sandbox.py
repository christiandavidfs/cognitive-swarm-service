"""Sandboxed shell — the agent proposes, the cage disposes. No external imports.

The small model is mediocre at reliable shell: it invents flags, chains
dangerously, hallucinates paths. So commands run JAILED:

  - cwd locked to a scratch dir (created per call, kept on failure for inspection)
  - wall timeout (default 30s), output capped at 8KB
  - env scrubbed (no *KEY*/*TOKEN* leak into the cage)
  - blocklist: rm -rf /, mkfs, :(){}, shutdown, sudo, ssh, nc/listen, chmod 777
  - write operations (>, >>, mkdir -p outside scratch, pip install, git push...)
    need approve=True (v2 autonomy ladder: drafts first, auto later)

Read-only probes (ls, cat, curl GET, python scripts/...) run free. Everything
returns {ok, code, out, err} — never raises, never escapes.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

_FORK = ":(" + "){:|:&};"
BLOCKED = re.compile(
    r"(rm\s+-rf\s+/( |$)|mkfs|shutdown|reboot|halt|sudo\s|ssh\s+|nc\s+-l|chmod\s+777|"
    r"curl[^|]*\|\s*(ba)?sh|wget[^|]*\|\s*(ba)?sh|>\s*/dev/(sda|nvme)|dd\s+if=)"
    + "|" + re.escape(_FORK),
    re.I,
)

TIMEOUT_S = 30
OUT_CAP = 8192


def _scrubbed_env() -> dict:
    keep = {k: v for k, v in os.environ.items()
            if not any(s in k.upper() for s in ("KEY", "TOKEN", "SECRET", "PASSWORD"))}
    keep.setdefault("PATH", "/usr/bin:/bin")
    keep["HOME"] = tempfile.gettempdir()
    return keep


def run(cmd: str, approve: bool = False, timeout_s: int = TIMEOUT_S,
        scratch: str = None) -> dict:
    """Run cmd caged. Writes need approve=True. Always returns a dict."""
    if BLOCKED.search(cmd):
        return {"ok": False, "code": -1, "out": "", "err": "blocked: dangerous pattern"}
    needs_approval = bool(re.search(r"(>>?|mkdir|pip\s+install|git\s+push|rm\s|mv\s|cp\s)", cmd))
    if needs_approval and not approve:
        return {"ok": False, "code": -2, "out": "",
                "err": "needs approval: re-run with approve=True (human gate, v2 ladder)"}
    workdir = scratch or tempfile.mkdtemp(prefix="cage-")
    try:
        p = subprocess.run(cmd, shell=True, cwd=workdir, env=_scrubbed_env(),
                           capture_output=True, text=True, timeout=timeout_s)
        out = (p.stdout or "")[-OUT_CAP:]
        err = (p.stderr or "")[-OUT_CAP:]
        return {"ok": p.returncode == 0, "code": p.returncode, "out": out,
                "err": err, "cwd": workdir}
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": -3, "out": "", "err": f"timeout after {timeout_s}s",
                "cwd": workdir}
    except Exception as e:
        return {"ok": False, "code": -4, "out": "", "err": f"{type(e).__name__}: {e}",
                "cwd": workdir}
