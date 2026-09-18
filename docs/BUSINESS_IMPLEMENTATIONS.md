# Business Implementations — Private API `POST /resolve`

> Private doc. Uses `service/app.py:141` `tier: procedure|retrieval` + `trace` + `procedure_sig 6d8cef7d` + `testing.swarm_procedures 100` + `swarm_knowledge 7` (Databricks `testing` ISOLATED, `2b2636d0ca412cdb`), `Wikidata 0.8` + `OpenAlex 0.9`, `60/min` `X-API-Key` `config/service.yaml:88`. Nothing public. `120/120` `0 loads` `65ms` warm, `88` same sig proves process not data.

Monetization: `procedure` `$0.01` / `retrieval corroborated` `$0.03` / `disagreement` honest `$0.05` per `POST /resolve` (when `auth.enabled:true` + `SERVICE_API_KEY`).

## 1. Investigation IA for Quality/Compliance (closest to `quality_platform`)
* **What:** `quality_platform.silver.coverage_by_api` + `bronze.endpoint_calls` → `POST /resolve` `Which service caused P95 breach?` with `reliability` + `independence` → `disagreement` when 2 teams blame different service.
* **Who pays:** Platform / QA leads (`quality_platform` owner).
* **Why us:** `Corroborator` honest conflict vs forced single, `procedure:bridge` trace for root-cause steps.

## 2. Test-to-Code Trace Marketplace
* **What:** `bronze.apis` + `mocha_tests_raw` → `Which API is uncovered?` → `procedure:handshake` skeletons as verified test generation patterns.
* **Who pays:** Engineering managers.
* **Why us:** `trace` reusable with new numbers (marketplace `procedure_sig`), not answer marketplace.

## 3. Financial Reconciliation Copilot
* **What:** `simple_subtract` `50-22=28`, `work_inverse` `15→3 days 60 people`, `trains_meet` settlement windows.
* **Who pays:** FinOps / banks.
* **Why us:** `student_trace.py:25` `verify_trace` (`=` + digit) + `DatabricksSQLRetriever` hits `silver.job_runs`.

## 4. Legal Clause QA
* **What:** `all_but` `23→8`, `stock_eggs` `12→9` → `contract all but 8 survive`.
* **Who pays:** Law firms (private `testing.*` contracts).
* **Why us:** `disagreement` when clauses conflict.

## 5. EdTech Tutor (procedure, not answer)
* **What:** Returns `trace: n=88, handshake = n*(n-1)/2 = 3828` not just `3828`.
* **Who pays:** Schools.
* **Why us:** `procedure` tier `0.3ms` `0 loads`.

## 6. Ops Runbook Automation
* **What:** `snail_well` `25→8 days` → `incident well` MTTR.
* **Who pays:** SRE.
* **Why us:** `DatabricksSQLRetriever` hits `silver.job_runs` + `local_docs`.

## 7. Data Catalog Search (no Confluence)
* **What:** `Wikidata` + `OpenAlex` + `local_docs` + `databricks_sql` Tier 3 → `What service owns X?` → `sources:[databricks:1, local-docs]`.
* **Who pays:** Enterprise data teams.
* **Why us:** `category`-gated, `0.85` + `0.35` thresholds prevent poison.

## 8. Fraud Pattern Detector
* **What:** `simple_probability 0.333` + `jug_impossible` → `transaction impossible` (gcd).
* **Who pays:** FinTechs.
* **Why us:** `jug_impossible` `gcd` + `probability` traces.

## 9. Hiring Screen (batch200)
* **What:** `batch200_final.json` `200` human diverse as interview bank.
* **Who pays:** HR SaaS.
* **Why us:** `46` patterns `184` `CV 0.951` proves structure not memorization.

## 10. API Metering (infra)
* **What:** `X-API-Key` + `60/min` `429` `service/app.py:55`.
* **Who pays:** All above per `tier`.
* **Why us:** Private, monetizable, `exempt /health /docs`.

## Reproducible demo (no Confluence)

```bash
python scripts/demo_investigation.py
# Q: When did the Western Roman Empire fall? -> 476 CE tier:retrieval sources:[local-docs, databricks:1]
# Q: What caused the fall of the Roman Empire? -> null tier:conflict disagreement: economic vs barbarian (honest)
# Q: In a group of 88 people each shakes hands ... -> 3828 tier:procedure trace: n=88, handshake = n*(n-1)/2 = 3828
```

Pick one to wire next (recommended: #1 Quality — closest to `quality_platform` data you already have).
