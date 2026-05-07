"""Unit tests for the recommender drivers package."""

from __future__ import annotations

from evidpath.domains.recommender.drivers import (
    HttpNativeDriverConfig,
    HttpNativeRecommenderDriver,
)


def test_http_native_driver_config_is_frozen() -> None:
    config = HttpNativeDriverConfig(base_url="http://localhost:8051", timeout_seconds=2.0)
    assert config.base_url == "http://localhost:8051"
    assert config.timeout_seconds == 2.0


def test_http_native_driver_config_compares_by_value() -> None:
    a = HttpNativeDriverConfig(base_url="http://x", timeout_seconds=1.0)
    b = HttpNativeDriverConfig(base_url="http://x", timeout_seconds=1.0)
    c = HttpNativeDriverConfig(base_url="http://y", timeout_seconds=1.0)
    assert a == b
    assert a != c


def test_http_native_recommender_driver_constructs_from_config() -> None:
    config = HttpNativeDriverConfig(base_url="http://example.com/", timeout_seconds=3.5)
    driver = HttpNativeRecommenderDriver(config)
    assert driver.base_url == "http://example.com"
    assert driver.timeout_seconds == 3.5


def test_http_native_recommender_driver_lives_in_drivers_package() -> None:
    assert HttpNativeRecommenderDriver.__module__ == (
        "evidpath.domains.recommender.drivers.http_native"
    )
