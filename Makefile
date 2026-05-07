STUDY_SLUG := 01-recommender-offline-eval
STUDY_DIR := studies/$(STUDY_SLUG)
STUDY_SRC := $(STUDY_DIR)/src
STUDY_NOTEBOOK := $(STUDY_DIR)/notebooks/offline_eval_demo.ipynb

.PHONY: sync install sync-hf lock lint format test test-slow ci build check-dist smoke-package \
	evidpath-help run canonical notebook study-test clean

sync:
	uv sync

install:
	uv sync

sync-hf:
	uv sync --group hf-example

lock:
	uv lock

evidpath-help:
	uv run evidpath --help

ci: lint test build check-dist smoke-package

lint:
	uv run ruff check .

format:
	uv run ruff format products/evidpath $(STUDY_SRC)

test:
	uv run pytest products/evidpath/tests -q

test-slow:
	uv run pytest products/evidpath/tests -q --run-slow

build:
	uv build --package evidpath --out-dir products/evidpath/dist

check-dist:
	uv run twine check products/evidpath/dist/*

smoke-package:
	uv run --no-project --with products/evidpath/dist/evidpath-*.whl evidpath --help
	uv run --no-project --with products/evidpath/dist/evidpath-*.whl python -m evidpath --help

run:
	PYTHONPATH=$(STUDY_SRC) uv run python -m recommender_offline_eval $(if $(CONFIG),--config $(CONFIG),) $(if $(OUTPUT_DIR),--output-dir $(OUTPUT_DIR),)

canonical:
	PYTHONPATH=$(STUDY_SRC) uv run python -m recommender_offline_eval --refresh-canonical

notebook:
	uv run jupyter notebook $(STUDY_NOTEBOOK)

study-test:
	PYTHONPATH=$(STUDY_SRC) uv run pytest studies/$(STUDY_SLUG)/tests

clean:
	rm -rf .ruff_cache $(STUDY_DIR)/.cache $(STUDY_DIR)/src/recommender_offline_eval/__pycache__
