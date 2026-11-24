PY ?= python3
export PYTHONPATH := src
WORKGROUP ?= retail-dw-wg

.PHONY: install demo test data deploy run bench dashboard teardown
install:   ## python deps
	$(PY) -m pip install -r requirements.txt
demo:      ## offline: SQL logic + dashboard on SQLite (no AWS)
	$(PY) -m rdw.local --rows 200000
test:
	$(PY) -m unittest discover -s tests -v
data:      ## 1M synthetic rows as Parquet
	$(PY) -m rdw.generate --rows 1000000 --out build/data
deploy:
	./scripts/deploy.shh
run:
	./scripts/run_pipeline.sh
bench:     ## tuned vs untuned timings on Redshift
	$(PY) -m rdw.bench --workgroup $(WORKGROUP)
dashboard: ## dashboard from Redshift
	$(PY) -m rdw.dashboard --backend redshift --workgroup $(WORKGROUP) --out build/dashboard.html
teardown:
	./scripts/teardown.sh
