"""Unit tests for the search drivers package."""

from __future__ import annotations

from evidpath.domains.search.drivers import (
    HttpNativeSearchDriver,
    HttpNativeSearchDriverConfig,
)


def test_http_native_search_driver_config_compares_by_value() -> None:
    a = HttpNativeSearchDriverConfig(base_url="http://x", timeout_seconds=1.0)
    b = HttpNativeSearchDriverConfig(base_url="http://x", timeout_seconds=1.0)
    c = HttpNativeSearchDriverConfig(base_url="http://y", timeout_seconds=1.0)
    assert a == b
    assert a != c


def test_http_native_search_driver_constructs_from_config() -> None:
    config = HttpNativeSearchDriverConfig(base_url="http://example.com/", timeout_seconds=3.5)
    driver = HttpNativeSearchDriver(config)
    assert driver.base_url == "http://example.com"
    assert driver.timeout_seconds == 3.5
