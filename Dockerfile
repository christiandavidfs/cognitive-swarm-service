FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*

# Self-contained build: context is THIS repo root (no sibling repos).
COPY pyproject.toml /app/pyproject.toml
COPY README.md /app/README.md
COPY config /app/config
COPY service /app/service
COPY tests /app/tests

RUN pip install --no-cache-dir -e /app

# Optional deterministic backend (uncomment + provide the package to enable):
# COPY ../cognitive-swarm /tmp/cognitive-swarm
# RUN pip install --no-cache-dir -e /tmp/cognitive-swarm

# Smoke test: service imports with zero backends installed (memory + retrieval serve).
RUN python -m py_compile service/app.py service/contracts.py service/router.py service/corroboration.py service/backends/*.py service/connectors/*.py service/memory/*.py service/models/*.py \
 && BACKENDS=__none__ python -c "from service.app import app; print('app ok, no backends required')"

EXPOSE 8000
CMD ["uvicorn", "service.app:app", "--host", "0.0.0.0", "--port", "8000"]
