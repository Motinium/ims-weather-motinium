"""Shared test setup.

The vendored library is loaded without importing the integration package,
whose __init__ pulls in Home Assistant. A stub parent module with the right
__path__ is enough for the relative imports inside weatheril to resolve.

Every fixture is a real IMS response captured from the live endpoints, so the
tests exercise the actual shapes without touching the network.
"""

import json
import pathlib
import sys
import types

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
COMPONENTS = REPO_ROOT / "custom_components"
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"

# Importable at collection time, so module-level imports in the test files work.
if str(COMPONENTS) not in sys.path:
    sys.path.insert(0, str(COMPONENTS))

# Endpoint URL -> fixture file. fetch_data() is patched to serve these.
FIXTURE_BY_URL = {
    "now_analysis/35": "now_analysis_35.json",
    "full_forecast_data/35": "full_forecast_35.json",
    "warnings_metadata": "warnings_metadata.json",
    "warnings": "warnings.json",
    "locations_info": "locations_info.json",
    "weather_codes": "weather_codes.json",
    "wind_directions": "wind_directions.json",
    "regions": "regions.json",
}


def load_fixture(name):
    with open(FIXTURES / name, encoding="utf-8") as handle:
        return json.load(handle)


def _install_stub_package():
    # If the real package is already imported (Home Assistant available), use
    # it: the weatheril subpackage does not depend on Home Assistant either way.
    if "ims_motinium" in sys.modules:
        return
    stub = types.ModuleType("ims_motinium")
    stub.__path__ = [str(COMPONENTS / "ims_motinium")]
    sys.modules["ims_motinium"] = stub


def _fake_fetch_data(url):
    """Stand in for utils.fetch_data, matching on the endpoint in the URL."""
    # warnings_metadata before warnings: the shorter name is a substring.
    for fragment, filename in FIXTURE_BY_URL.items():
        if fragment in url:
            return load_fixture(filename)
    raise AssertionError(f"No fixture for {url}")


@pytest.fixture
def weather(monkeypatch):
    """A WeatherIL wired to the fixtures instead of the network."""
    _install_stub_package()
    from ims_motinium.weatheril import utils as weatheril_utils
    from ims_motinium import weatheril as weatheril_pkg

    # Lookup tables are module-level and cached for the process; clear them so
    # each test starts from the fixtures rather than a previous test's data.
    for name in (
        "_weather_code_map",
        "_locations_map",
        "_wind_direction_map",
        "_regions_map",
        "_warning_type_map",
        "_warning_group_map",
        "_warning_severity_map",
    ):
        monkeypatch.setattr(weatheril_utils, name, {}, raising=False)

    monkeypatch.setattr(weatheril_utils, "fetch_data", _fake_fetch_data)
    monkeypatch.setattr(weatheril_pkg, "fetch_data", _fake_fetch_data)

    def _no_network(*args, **kwargs):
        raise AssertionError("test made a real HTTP request")

    monkeypatch.setattr(weatheril_utils._session, "get", _no_network)

    return weatheril_pkg.WeatherIL("35", "en")
