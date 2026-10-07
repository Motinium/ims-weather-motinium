"""Tests for setting up a config entry.

Like the digest and entity tests these import the integration, so they need
Home Assistant and are skipped when it is not installed. The coordinator is a
stand-in: what is under test is which coordinator a setup ends up using.
"""

import asyncio
import types

import pytest

pytest.importorskip("homeassistant", reason="Home Assistant is not installed")

import ims_motinium
from homeassistant.exceptions import ConfigEntryNotReady


def _entry(entry_id):
    return types.SimpleNamespace(
        entry_id=entry_id,
        data={
            "name": "IMS Weather",
            "city": 35,
            "language": "en",
            "update_interval": 60,
            "ims_platform": ["Sensor", "Weather"],
        },
        options={},
        add_update_listener=lambda listener: lambda: None,
    )


def _hass():
    async def forward_entry_setups(entry, platforms):
        return None

    return types.SimpleNamespace(
        data={},
        config_entries=types.SimpleNamespace(
            async_forward_entry_setups=forward_entry_setups
        ),
        services=types.SimpleNamespace(
            has_service=lambda domain, service: True,
            async_register=lambda *args: None,
        ),
    )


@pytest.mark.parametrize("next_entry", ["same", "new"], ids=["retry", "re-added"])
def test_a_setup_after_a_failed_one_builds_its_own_coordinator(monkeypatch, next_entry):
    """IMS unreachable at setup left the integration unable to load at all.

    The coordinator was cached per location before its first refresh. When
    that refresh failed, Home Assistant shut the coordinator down, and every
    later setup reused the dead one: the retries never loaded even with IMS
    back, and an entry added again in its place failed with "called when
    config entry state is NOT_LOADED", the removed entry's state.
    """
    built = []
    ims = types.SimpleNamespace(down=True)

    class Coordinator:
        def __init__(self, *args, config_entry=None, **kwargs):
            self.config_entry = config_entry
            built.append(self)

        async def async_config_entry_first_refresh(self):
            if ims.down:
                raise ConfigEntryNotReady("IMS current analysis unavailable")

    monkeypatch.setattr(ims_motinium, "WeatherUpdateCoordinator", Coordinator)
    hass = _hass()
    first = _entry("first")
    second = first if next_entry == "same" else _entry("second")

    with pytest.raises(ConfigEntryNotReady):
        asyncio.run(ims_motinium.async_setup_entry(hass, first))
    ims.down = False
    assert asyncio.run(ims_motinium.async_setup_entry(hass, second))

    assert [c.config_entry for c in built] == [first, second]
    in_use = hass.data[ims_motinium.DOMAIN][second.entry_id]
    assert in_use[ims_motinium.ENTRY_WEATHER_COORDINATOR] is built[1]
