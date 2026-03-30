STUDY_SLUG := 01-recommender-offline-eval
STUDY_DIR := studies/$(STUDY_SLUG)
STUDY_SRC := $(STUDY_DIR)/src
STUDY_NOTEBOOK := $(STUDY_DIR)/notebooks/offline_eval_demo.ipynb
STUDY_REQUIREMENTS := $(STUDY_DIR)/requirements.txt

.PHONY: install lint format run notebook clean

install:
	.venv/bin/python -m pip install -r requirements.txt -r $(STUDY_REQUIREMENTS)

lint:
	.venv/bin/ruff check .

format:
	.venv/bin/ruff format $(STUDY_SRC)

run:
	PYTHONPATH=$(STUDY_SRC) .venv/bin/python -m recommender_offline_eval

notebook:
	.venv/bin/jupyter notebook $(STUDY_NOTEBOOK)

clean:
	rm -rf .ruff_cache $(STUDY_DIR)/.cache $(STUDY_DIR)/src/recommender_offline_eval/__pycache__
