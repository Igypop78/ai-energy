"""Testy s Home Assistant (pytest-homeassistant-custom-component) – bežia v GitHub Actions."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield
