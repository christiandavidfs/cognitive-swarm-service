"""Auth + rate-limit guard — extracted from service/app.py (fase 3 of plan/remediacion-hallazgos.md).

Pure move, zero behavior change: same status codes, same headers, same helpers.
app.py registers the middleware with one line and keeps importing the pure
helpers (expand_api_keys / bucket_key / auth_decision) so existing tests and
callers stay unchanged.

The middleware takes its auth-config loader as a parameter (factory) so the
caller's module namespace stays the single patch point (tests monkeypatch
``service.app._auth_config``).
"""
from __future__ import annotations

import os
import re
import time
import collections
from pathlib import Path
from typing import Iterable, List, Optional, Set

from fastapi import Request
from fastapi.responses import JSONResponse

# Cache parsed YAML so we don't re-read disk on every request. Invalidated on mtime change.
_auth_cache: dict = {"mtime": 0.0, "config": None}
_auth_cache_ttl_s = 30.0
_auth_cache_ts = 0.0

_rate_buckets: dict = {}
_rate_lock = None
try:
    import threading as _thr
    _rate_lock = _thr.Lock()
except Exception:
    _rate_lock = None

_MAX_RATE_BUCKETS = 10000

_RATE_WINDOW_S = 60.0


def _sweep_rate_buckets(now: float, window: float = 60.0):
    """Drop expired entries; cap dict size so idle keys can't grow memory unbounded."""
    for key in list(_rate_buckets.keys()):
        dq = _rate_buckets.get(key)
        if dq is None:
            continue
        while dq and dq[0] <= now - window:
            dq.popleft()
        if not dq:
            del _rate_buckets[key]
    if len(_rate_buckets) > _MAX_RATE_BUCKETS:
        # Evict oldest-touched buckets first (best effort)
        for key in list(_rate_buckets.keys())[: len(_rate_buckets) - _MAX_RATE_BUCKETS]:
            del _rate_buckets[key]


def _auth_config():
    global _auth_cache_ts
    cfg_path = Path(__file__).parent.parent / "config" / "service.yaml"
    now = time.time()
    cached = _auth_cache.get("config")
    if cached is not None and (now - _auth_cache_ts) < _auth_cache_ttl_s:
        try:
            if cfg_path.stat().st_mtime == _auth_cache.get("mtime"):
                return cached
        except Exception:
            return cached
    try:
        import yaml
        mtime = cfg_path.stat().st_mtime
        data = yaml.safe_load(cfg_path.read_text()) or {}
        auth = data.get("auth", {}) if isinstance(data, dict) else {}
        return_cfg = {
            "enabled": bool(auth.get("enabled", False)),
            "keys": expand_api_keys(auth.get("api_keys") or []),
            "limit": int(auth.get("rate_limit_per_min", 60)),
            "exempt": set(auth.get("exempt_paths") or ["/health", "/docs", "/openapi.json", "/redoc"]),
        }
        _auth_cache["mtime"] = mtime
        _auth_cache["config"] = return_cfg
        _auth_cache_ts = now
        return return_cfg
    except Exception:
        if _auth_cache.get("config") is not None:
            return _auth_cache["config"]
        return {"enabled": False, "keys": set(), "limit": 60, "exempt": {"/health", "/docs", "/openapi.json", "/redoc"}}

_ENV_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|%([A-Za-z_][A-Za-z0-9_]*)%")


def expand_api_keys(raw_keys: Optional[Iterable]) -> Set[str]:
    """Expand env placeholders in configured API keys.

    Unexpanded ``${VAR}`` / ``%VAR%`` is dropped. An enabled auth block with
    zero keys after expansion must fail closed, not accept any caller.
    Comma-split only when expansion changed the value (an env list).
    """
    found: List[str] = []
    for raw in raw_keys or []:
        if not isinstance(raw, str):
            continue
        original = raw.strip()
        if not original:
            continue

        def _replace(match: re.Match) -> str:
            name = match.group(1) or match.group(2)
            return os.environ.get(name, match.group(0))

        expanded = os.path.expandvars(_ENV_PLACEHOLDER.sub(_replace, original))
        if "${" in expanded or _ENV_PLACEHOLDER.search(expanded):
            continue
        expanded = expanded.strip()
        if not expanded:
            continue
        if expanded != original and "," in expanded:
            found.extend(part.strip() for part in expanded.split(",") if part.strip())
        else:
            found.append(expanded)
    return set(found)


def bucket_key(provided: str, client_host: Optional[str]) -> str:
    """Rate-limit identity. A present key always wins, even if ``client`` is missing.

    The old ``provided or host if client else "anon"`` expression collapsed every
    request onto one bucket whenever ``request.client`` was None.
    """
    if provided:
        return provided
    if client_host:
        return client_host
    return "anon"


def auth_decision(enabled: bool, keys: Set[str], provided: str, exempt: bool) -> int:
    """200 to continue, 401 to reject. Disabled and exempt paths never look at keys.

    Enabled with an empty key set is a misconfiguration: reject everyone, including
    callers who sent a key. Otherwise require an exact match.
    """
    if not enabled or exempt:
        return 200
    if not keys or provided not in keys:
        return 401
    return 200


def _provided_api_key(headers) -> str:
    provided = (headers.get("x-api-key") or "").strip()
    if provided:
        return provided
    auth_h = headers.get("authorization") or ""
    if auth_h.lower().startswith("bearer "):
        return auth_h[7:].strip()
    return ""


def build_auth_rate_middleware(auth_config_loader):
    """Return the ASGI http middleware bound to ``auth_config_loader``.

    Why a factory instead of reading config directly: the loader is resolved at
    request time from the caller's namespace, so tests can monkeypatch
    ``service.app._auth_config`` without touching this module.
    """

    async def _auth_rate_middleware(request: Request, call_next):
        cfg = auth_config_loader()
        path = request.url.path
        exempt = path in cfg["exempt"]
        provided = _provided_api_key(request.headers)
        if auth_decision(cfg["enabled"], cfg["keys"], provided, exempt) == 401:
            detail = (
                "Auth enabled but no API keys configured."
                if not cfg["keys"]
                else "Invalid API key. Provide X-API-Key or Authorization: Bearer <key>."
            )
            return JSONResponse(status_code=401, content={"detail": detail})
        if cfg["enabled"] and not exempt:
            # rate-limit per key (or IP fallback) — only after a key was accepted
            bkey = bucket_key(provided, request.client.host if request.client else None)
            now = time.time()
            window = _RATE_WINDOW_S
            limit = cfg["limit"]
            # simple sliding window
            if _rate_lock:
                with _rate_lock:
                    dq = _rate_buckets.get(bkey)
                    if dq is None:
                        dq = collections.deque()
                        _rate_buckets[bkey] = dq
                    # purge old
                    while dq and dq[0] <= now - window:
                        dq.popleft()
                    if not dq and len(_rate_buckets) > _MAX_RATE_BUCKETS:
                        _sweep_rate_buckets(now, window)
                        dq = _rate_buckets.get(bkey)
                        if dq is None:
                            dq = collections.deque()
                            _rate_buckets[bkey] = dq
                    if len(dq) >= limit:
                        return JSONResponse(status_code=429, content={"detail": f"Rate limit {limit}/min exceeded", "retry_after": int(dq[0] + window - now) + 1})
                    dq.append(now)
            else:
                dq = _rate_buckets.get(bkey)
                if dq is None:
                    dq = collections.deque()
                    _rate_buckets[bkey] = dq
                while dq and dq[0] <= now - window:
                    dq.popleft()
                if len(dq) >= limit:
                    return JSONResponse(status_code=429, content={"detail": f"Rate limit {limit}/min exceeded"})
                dq.append(now)
        response = await call_next(request)
        # monetization header
        if cfg["enabled"]:
            response.headers["X-RateLimit-Limit"] = str(cfg["limit"])
        return response

    return _auth_rate_middleware