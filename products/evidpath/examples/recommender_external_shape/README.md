# External-Shape Recommender Example

Run an audit against an HTTP recommender whose request and response shape is not
Evidpath's native contract.

```sh
python -m examples.recommender_external_shape.server
```

```sh
.venv/bin/evidpath audit \
  --domain recommender \
  --driver-config-path examples/recommender_external_shape/driver_config.json \
  --output-dir /tmp/external-shape-audit
```
