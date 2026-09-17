"""Model registry — pluggable, per-request choosable, scales to N models.

Mirrors the connector registry: declare models in `config/service.yaml` (one block per
model), registry builds them, `POST /resolve {models: [...]}` overrides defaults.

Supports two backends today (extend without router change):
  - type: mlx  → local MLXBackend via `cognitive_swarm.models.backend` / `multi_backend.py`
  - type: api  → OpenAI-compatible HTTP (OpenRouter, etc.)

The service never assumes all models fit in RAM — MLX models load sequentially
(one at a time) like the core `MultiModelBackend`. API models are just HTTP.
"""
from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Dict, List, Optional

import yaml
import requests

logger = logging.getLogger(__name__)

SERVICE_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "service.yaml"

# Single shared MultiModelBackend for MLX — constructed lazily so import doesn't need mlx.
_MLX_BACKEND = None

def _get_mlx_backend():
    global _MLX_BACKEND
    if _MLX_BACKEND is not None:
        return _MLX_BACKEND
    # Defer import — allows running tests without mlx installed
    try:
        from cognitive_swarm.models.multi_backend import MultiModelBackend
        _MLX_BACKEND = MultiModelBackend()
        return _MLX_BACKEND
    except Exception as e:
        logger.debug("MLX backend unavailable: %s", e)
        return None

def _expand_env(value):
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value

def _read_models_config(path: Optional[Path] = None) -> Dict[str, dict]:
    cfg_path = Path(path) if path else SERVICE_CONFIG_PATH
    if not cfg_path.exists():
        return {}
    try:
        data = yaml.safe_load(cfg_path.read_text()) or {}
        models = data.get("models", {}) if isinstance(data, dict) else {}
        return {k: _expand_env(v) for k, v in models.items()} if isinstance(models, dict) else {}
    except Exception:
        return {}

def available_models(config_path: Optional[Path] = None) -> List[dict]:
    cfg = _read_models_config(config_path)
    out = []
    for name, opts in sorted(cfg.items()):
        out.append({
            "name": name,
            "type": opts.get("type"),
            "enabled": bool(opts.get("enabled", False)),
            "strengths": opts.get("strengths", []),
            "path": opts.get("path") or opts.get("model"),
        })
    return out

def default_enabled_models(config_path: Optional[Path] = None) -> List[str]:
    cfg = _read_models_config(config_path)
    return [n for n, o in cfg.items() if o.get("enabled")]

def ensure_mlx_models_registered(config_path: Optional[Path] = None):
    """Register any mlx models from service.yaml that aren't in the default MultiModelBackend."""
    backend = _get_mlx_backend()
    if backend is None:
        return
    cfg = _read_models_config(config_path)
    for name, opts in cfg.items():
        if opts.get("type") != "mlx":
            continue
        if name in backend.models:
            continue
        try:
            backend.register_model(
                name=name,
                path=opts.get("path", ""),
                description=opts.get("description", name),
                strengths=opts.get("strengths", []),
                ram_estimate_gb=float(opts.get("ram_gb", 2.0)),
            )
        except Exception as e:
            logger.debug("Register model %s failed: %s", name, e)

def list_models(config_path: Optional[Path] = None) -> List[dict]:
    """List all known models with loaded flag (for GET /models)."""
    ensure_mlx_models_registered(config_path)
    backend = _get_mlx_backend()
    mlx_list = backend.list_models() if backend else []
    mlx_by_name = {m["name"]: m for m in mlx_list}
    cfg = _read_models_config(config_path)
    out = []
    for name, opts in sorted(cfg.items()):
        entry = {
            "name": name,
            "type": opts.get("type"),
            "enabled": bool(opts.get("enabled", False)),
            "strengths": opts.get("strengths", []),
            "path": opts.get("path") or opts.get("model"),
            "base_url": opts.get("base_url"),
        }
        if name in mlx_by_name:
            entry["loaded"] = mlx_by_name[name].get("loaded", False)
            entry["ram_gb"] = mlx_by_name[name].get("ram_gb")
        else:
            entry["loaded"] = False
        out.append(entry)
    return out

def generate_with_model(
    model_name: str,
    prompt: str,
    max_tokens: int = 16,
    temperature: float = 0.7,
    config_path: Optional[Path] = None,
) -> str:
    """Generate with a chosen model name (mlx or api). Raises on unknown/disabled."""
    cfg = _read_models_config(config_path)
    opts = cfg.get(model_name)
    if not opts or not opts.get("enabled"):
        # Allow phi/qwen defaults even if not in service.yaml (core defaults)
        if model_name in ("phi", "qwen"):
            opts = {"type": "mlx", "enabled": True}
        else:
            raise ValueError(f"Model {model_name!r} not enabled. Available: {list(cfg.keys())}")
    mtype = opts.get("type", "mlx")
    if mtype == "mlx":
        ensure_mlx_models_registered(config_path)
        backend = _get_mlx_backend()
        if backend is None:
            raise RuntimeError("MLX backend not available (mlx not installed)")
        # Load on demand (sequential)
        backend.load_model(model_name, max_tokens=max_tokens, temperature=temperature)
        resp = backend.generate(prompt)
        # backend.generate may return object with .text
        if hasattr(resp, "text"):
            return resp.text
        if isinstance(resp, str):
            return resp
        return str(resp)
    elif mtype == "api":
        base_url = _expand_env(opts.get("base_url", "")).rstrip("/")
        model = opts.get("model", model_name)
        api_key_env = opts.get("api_key_env", "OPENROUTER_API_KEY")
        api_key = os.getenv(api_key_env, "")
        if not api_key:
            raise RuntimeError(f"API model {model_name} needs env {api_key_env}")
        # OpenAI-compatible chat completions (OpenRouter)
        url = f"{base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        r = requests.post(url, json=body, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        try:
            return data["choices"][0]["message"]["content"]
        except Exception:
            return str(data)
    else:
        raise ValueError(f"Unknown model type {mtype!r} for {model_name}")
