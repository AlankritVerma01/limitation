# CSV Dataset Schema

Custom datasets use a directory with exactly two required files:

- `interactions.csv`
- `items.csv`

## `interactions.csv`

Required columns:

- `user_id`
- `item_id`
- `rating`
- `timestamp`

Expectations:

- ids should be integer or integer-like values
- `rating` should be numeric
- `timestamp` should be numeric and sortable in chronological order

## `items.csv`

Required columns:

- `item_id`
- `title`

Feature columns:

- every remaining numeric or boolean column is treated as an item feature
- non-numeric columns are ignored
- feature columns are optional for popularity-only runs

When features are required:

- the built-in `genre_profile` model uses them directly
- if you configure `genre_profile` without any numeric or boolean item feature columns, the run fails with a clear error
- popularity-only comparisons can still run on featureless items

## Minimal Example

```text
my_dataset/
  interactions.csv
  items.csv
```

Example commands:

```bash
PYTHONPATH=studies/01-recommender-offline-eval/src \
  .venv/bin/python -m recommender_offline_eval \
  --config studies/01-recommender-offline-eval/examples/custom_csv_run.json
```
