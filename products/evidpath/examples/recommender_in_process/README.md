# In-Process Recommender Example

Run an audit against a Python recommender without starting an HTTP server.

```sh
PYTHONPATH=. .venv/bin/evidpath audit \
  --domain recommender \
  --driver-config-path examples/recommender_in_process/driver_config.json \
  --output-dir /tmp/in-process-audit
```
