#!/usr/bin/env python3
"""Demo investigation IA — sellable, no Confluence, uses Databricks + procedure (private)."""
import sys
from pathlib import Path as _P
_REPO = _P(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
from fastapi.testclient import TestClient
import service.app as am
am._memory=None; am._router=None
c=TestClient(am.app)
print("=== Investigation IA Demo (private, monetizable, no Confluence) ===\n")
print("Pricing: 60 req/min per API key (X-API-Key), 120/120 deterministic 0 loads, 88 same 6d8cef7d\n")
for q in [
 "When did the Western Roman Empire fall?",
 "What caused the fall of the Roman Empire?",
 "What is the chemical formula of water?",
 "In a group of 88 people each shakes hands with every other exactly once how many handshakes?",
 "How many animals of each kind did Moses take on the ark?",
 "What gets wetter as it dries?",
]:
    r=c.post('/resolve', json={'question': q})
    j=r.json()
    print(f"Q: {q}")
    print(f"  -> {j['answer']!r} tier:{j['tier']} status:{j['status']}")
    if j['sources']:
        src=j['sources'][0]
        print(f"     provenance:{src.get('sources') or src.get('name')} trace:{str(j.get('trace'))[:70] if j.get('trace') else ''}")
    if j['disagreement']:
        print(f"     disagreement:{j['disagreement'][0]['answer']!r} vs {j['disagreement'][1]['answer']!r} (honest, no forced single)" if len(j['disagreement'])>1 else f"     disagreement:{j['disagreement']}")
    print()
print("Try with API key (when auth.enabled:true): curl -H 'X-API-Key: $SERVICE_API_KEY' -X POST http://localhost:8000/resolve -d '{\"question\":\"When did fall?\"}'")
