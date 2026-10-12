"""Shared HTTP fetch with backoff for scheduled jobs. No external imports."""
from __future__ import annotations

import time

import requests

UA = {"User-Agent": "Mozilla/5.0"}


def fetch_json(url: str, params=None, timeout_s: int = 15, retries: int = 3,
               headers=None):
    """GET JSON with exponential backoff. Raises the last error."""
    last = None
    for i in range(retries):
        try:
            r = requests.get(url, params=params, headers=headers or UA, timeout=timeout_s)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            time.sleep(2 ** i)
    raise last
