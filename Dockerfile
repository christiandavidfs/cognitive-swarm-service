FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential && rm -rf /var/lib/apt/lists/*

# Core first (cache layer) — copy swarm core alongside service
COPY cognitive-swarm/ /tmp/cognitive-swarm/

# Service
COPY cognitive-swarm-service/pyproject.toml /app/pyproject.toml
COPY cognitive-swarm-service/README.md /app/README.md
COPY cognitive-swarm-service/config /app/config
COPY cognitive-swarm-service/service /app/service
COPY cognitive-swarm-service/tests /app/tests

# Install core + service
RUN pip install --no-cache-dir -e /tmp/cognitive-swarm \
 && pip install --no-cache-dir -e /app

# Validate deterministic hierarchy before serving (0 model loads)
RUN python -m py_compile service/app.py service/connectors/*.py service/memory/*.py service/models/*.py \
 && python -c "from cognitive_swarm.orchestration.truth_router import TruthRouter; r=TruthRouter(); print('router ok', r.resolve('What does print(2+3) output?').answer)"

EXPOSE 8000
CMD ["uvicorn", "service.app:app", "--host", "0.0.0.0", "--port", "8000"]
