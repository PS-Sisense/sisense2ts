import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def raw_datamodel() -> dict:
    return json.loads((FIXTURES / "datamodel_sample.json").read_text())


@pytest.fixture
def raw_dashboard() -> dict:
    return json.loads((FIXTURES / "dashboard_sample.json").read_text())


@pytest.fixture
def raw_dashboard_rich() -> dict:
    """A broader sample dashboard for development/demo: many chart types, all filter
    kinds, a translatable calc, and one UNSUPPORTED calc (YoY growth) for the report."""
    return json.loads((FIXTURES / "dashboard_rich.json").read_text())
