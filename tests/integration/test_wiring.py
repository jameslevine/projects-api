"""Regression tests for the real dependency wiring (no dependency_overrides).

The other integration tests override `get_repository`, which hid a bug where the cached
repository factory was keyed on an unhashable Settings object and raised on every request.
"""

import json
from typing import Any

from projects_api.api import deps
from projects_api.config import Settings, get_settings
from tests.integration.test_projects_api import _apigw_event, _Ctx


def test_settings_are_hashable_and_cached() -> None:
    assert hash(get_settings()) == hash(get_settings())
    assert isinstance(Settings(), Settings)


def test_get_repository_returns_a_single_cached_instance(dynamodb_table: Any) -> None:
    deps._repository.cache_clear()
    first = deps.get_repository()
    assert first is deps.get_repository()
    deps._repository.cache_clear()


def test_handler_creates_project_with_real_wiring(dynamodb_table: Any) -> None:
    from projects_api.main import app, handler

    assert not app.dependency_overrides, "this test must run without overrides"
    deps._repository.cache_clear()
    try:
        resp = handler(
            _apigw_event("POST", "/v1/projects", {"name": "real wiring", "type": "mcp"}, "k-real"),
            _Ctx(),
        )
        assert resp["statusCode"] == 201, resp
        assert json.loads(resp["body"])["ownerId"] == "k-real"
    finally:
        deps._repository.cache_clear()
