"""Shared urllib helper for HTTP recommender drivers."""

from __future__ import annotations

import json
from urllib import request
from urllib.error import HTTPError, URLError


def request_json(
    req: request.Request,
    *,
    timeout: float,
    purpose: str,
) -> dict | list:
    """Issue an HTTP request and parse the JSON response."""
    target = req.full_url
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(
            f"Recommender target failed during {purpose}: HTTP {exc.code} from {target}."
        ) from exc
    except URLError as exc:
        raise RuntimeError(
            f"Recommender target was unreachable during {purpose}: {target}."
        ) from exc
    except TimeoutError as exc:
        raise RuntimeError(
            f"Recommender target timed out during {purpose}: {target}."
        ) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Recommender target returned malformed JSON during {purpose}: {target}."
        ) from exc
