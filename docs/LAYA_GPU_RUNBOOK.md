# LAYA Gate A/B — Runbook para máquina con GPU

> Esta VM de desarrollo **no tiene GPU** — Gate A parcial quedó registrado en
> `docs/MEASUREMENTS.md` (LAYA zero-shot 2/12 en taxonomía, latencia CPU
> 11–42 s/call = veredicto de hardware). Este runbook es TODO lo que falta
> para cerrar los gates en la máquina con GPU.

## 0. Contexto — qué se está midiendo y por qué

| Gate | Pregunta | Regla de promoción |
|------|----------|--------------------|
| **A** | ¿LAYA zero-shot sirve como juez en nuestras tareas? | Solo informativo — se espera NO (vendor admite 0.362 base near-chance) |
| **B** | ¿El checkpoint fine-tuned (`typed-decisions`) o un fine-tune nuestro supera a Kev? | `err@0.9 ≤ 0.062` a `coverage ≥ 73%` (baseline Kev: acc 0.900, Brier 0.176, auto@0.9 146/200 err 0.062) |

Todo va contra el mismo seam (`service/judgments/laya.py`, `adjudicate.py`) —
ningún resultado requiere tocar código de ruteo.

## 1. Setup (una vez)

```bash
# venv en ruta CORTA (Windows rompe con rutas largas de torch; en Linux da igual)
python -m venv C:/venvs/laya          # o ~/venvs/laya
C:/venvs/laya/Scripts/pip install --upgrade pip    # Linux: venv/bin/pip
C:/venvs/laya/Scripts/pip install "laya[serve]" datasets

# Verificar
C:/venvs/laya/Scripts/python -c "import laya, torch; print(laya.__version__, torch.cuda.is_available())"
# → debe imprimir algo como "0.3.22 True" — si cuda.is_available() es False, parar aquí
```

**Gotcha del vendor**: si TensorFlow está instalado en esa máquina, correr
todo con `USE_TF=0` (TF/abseil puede deadlockear la construcción del modelo).

Primer uso descarga el checkpoint (~808 MB english; typed-decisions se baja
solo si se pide). Para agnews hace falta `datasets`.

## 2. Gate A/B — bench directo por SDK (RECOMENDADO en GPU)

Sin HTTP, carga el checkpoint en proceso — es la única vía fiable para el
subfolder `typed-decisions`:

```bash
# 2a. Taxonomía nuestra (12 casos — comparable con measure_jev_classify de Kev)
C:/venvs/laya/Scripts/python scripts/bench_laya_sdk.py \
    --suite taxonomy --checkpoint english --save data/laya_en_tax.preds.jsonl

# 2b. AG News — la MISMA slice que el piloto Kev (test[1000:1200], n=200)
C:/venvs/laya/Scripts/python scripts/bench_laya_sdk.py \
    --suite agnews --checkpoint english --offset 1000 --n 200 \
    --save data/laya_en_agnews.preds.jsonl

# 2c. EL ATAJO: checkpoint ya fine-tuned (Gate B sin gastar nuestro entrenamiento)
C:/venvs/laya/Scripts/python scripts/bench_laya_sdk.py \
    --suite agnews --checkpoint typed-decisions --offset 1000 --n 200 \
    --save data/laya_td_agnews.preds.jsonl

# 2d. Suite de taxonomía con el checkpoint fine-tuned (¿arregla el 2/12?)
C:/venvs/laya/Scripts/python scripts/bench_laya_sdk.py \
    --suite taxonomy --checkpoint typed-decisions --save data/laya_td_tax.preds.jsonl
```

Salida esperada por corrida: acc, Brier, coverage@0.9, err@0.9, latencia
mean/p95, y las baselines de Kev impresas al pie para comparación directa.

## 3. Gate A vía HTTP — la ruta del ensemble (opcional, valida el wiring)

Esta valida el adaptador + Juicio 3 tal como servirían en producción:

```bash
# Servidor oficial, Jev-compatible en :8000 (misma API que jev.py)
LAYA_DEVICE=cuda LAYA_PRELOAD=1 C:/venvs/laya/Scripts/laya-serve &
# Linux: LAYA_DEVICE=cuda LAYA_PRELOAD=1 ~/venvs/laya/bin/laya-serve &

# Warm-up: la 1ª llamada compila caches (~5-20 s incluso en CPU)
curl -s -m 120 localhost:8000/v1/systemone -H 'Content-Type: application/json' \
  -d '{"state":"What is 5+3?","questions":{"t":{"type":"choice","instructions":"classify","criteria":{"math":"arithmetic","code":"code","reasoning":"story problem"}}}}'

# Bench del repo (usa el adaptador + fallbacks reales)
LAYA_BASE_URL=http://127.0.0.1:8000 LAYA_TIMEOUT_S=60 \
  python scripts/bench_laya.py

# Con Juicio 3 (ensemble LAYA+secundario+árbitro) — solo si hay Kev/Jev disponible:
LAYA_BASE_URL=http://127.0.0.1:8000 LAYA_TIMEOUT_S=60 JUDGE_ADJUDICATE=1 \
  [LAYA_SECONDARY=jev con KEV_BASE_URL o TYPESAFE_API_KEY] \
  python scripts/bench_laya.py
```

> ⚠️ El bench HTTP y el SDK no son comparables entre sí en latencia (HTTP
> añade serialización); para comparar contra Kev usa SIEMPRE la misma vía
> que usó el piloto Kev (`pilot_agnews.py` → SDK `bench_laya_sdk.py`).

## 4. Gate B — temperature fitting (OBLIGATORIO antes de confiar en probs)

El vendor lo dice en su propia card: base ships over-confident (ECE 0.466 →
0.081 tras refit por (tipo, n_opciones)). Con los preds JSONL del paso 2:

```bash
python scripts/fit_laya_temperature.py data/laya_td_agnews.preds.jsonl
# → tabla T* por grupo + línea recomendada:
#   LAYA_TEMPERATURE=1.20
```

Aplicarlo es solo env — el adaptador ya lo consume:

```bash
LAYA_TEMPERATURE=<T* del paso anterior> python scripts/bench_laya_sdk.py ...  # re-medir
```

El gate de promoción se evalúa con la temperatura YA ajustada, no con la cruda.

## 5. (Opcional) Fine-tune con labels propias

Solo si `typed-decisions` no alcanza el gate sobre NUESTRA taxonomía:

```bash
# Exportar labels (≥400 recomendado; AG News labels son gratis y regenerables)
python scripts/export_laya_jsonl.py --from-csv labels.csv -o data/laya_ft.jsonl
# El shape del record es POC — verificar contra el notebook oficial ANTES de entrenar:
#   github.com/NandhaKishorM/laya → notebooks/laya_finetune_typed_decisions_2xT4_kaggle.ipynb
# (el notebook corre entero en Kaggle gratis 2x T4 — no necesita GPU propia)
```

## 6. Cierre del gate — qué registrar

1. Copiar la salida completa de cada corrida a `docs/MEASUREMENTS.md`
   (sección nueva con fecha, formato igual a las entradas anteriores).
2. Veredicto explícito: `GATE A: PASS/FAIL` · `GATE B: PASS/FAIL` contra la
   regla `err@0.9 ≤ 0.062 @ coverage ≥ 73%`.
3. Si GATE B pasa → promover por asiento en `config/service.yaml`
   (`judge.seats.classify: laya` + `LAYA_TEMPERATURE=<T*>`), shadow week,
   rollback = una línea. Si falla → queda documentado como "no apto para
   asiento 1" y el debate termina con un número, no con un blog post.
4. Actualizar `AGENTS.md` (sección State) con los resultados.

## Troubleshooting

| Síntoma | Causa probable | Fix |
|---|---|---|
| `WinError 206 filename too long` al instalar | Python WindowsApps + torch paths largos | venv en ruta corta (`C:/venvs/laya`) |
| `laya.load()` cuelga | TF instalado (abseil deadlock) | `USE_TF=0` antes del comando |
| Timeout en 1ª llamada | warm-up del checkpoint | reintentar; en GPU el warm-up es ~segundos |
| `err@0.9` alto con acc alta | probs over-confident sin refit | paso 4 obligatorio |
| `noul` confiado y erróneo | issue vendor #156 (label-following) | usar `choice` 2-opciones con keys neutras (ver card) |
| Latencia alta en GPU | TileLang fast path sin activar | `pip install "laya[fast]"` o aceptar la ruta estándar (~35 ms T4) |
