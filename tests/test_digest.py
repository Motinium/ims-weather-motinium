"""Tests for the daily digest rules.

These import the integration itself, so they need Home Assistant available and
are skipped when it is not.
"""

import pytest

pytest.importorskip("homeassistant", reason="Home Assistant is not installed")

from ims_motinium.const import DAILY_DIGEST_RULES
from ims_motinium.sensor import generate_daily_digest


class _Hour:
    """Minimal stand-in for weatheril's Hourly."""

    def __init__(self, hour, **fields):
        self.hour = hour
        self.temperature = fields.get("temperature")
        self.precise_temperature = fields.get("precise_temperature")
        self.heat_stress_level = fields.get("heat_stress_level")
        self.u_v_index = fields.get("u_v_index")
        self.gust_speed = fields.get("gust_speed")
        self.wind_speed = fields.get("wind_speed")
        self.pm10 = fields.get("pm10")
        self.rain_chance = fields.get("rain_chance")
        self.rain = fields.get("rain")


class _Day:
    def __init__(self, hours):
        self.hours = hours


def _quiet_day():
    """Ordinary summer values: below every threshold."""
    return _Day(
        [
            _Hour(f"{h:02d}:00", precise_temperature=28.0, u_v_index=3, gust_speed=20)
            for h in range(24)
        ]
    )


def test_ordinary_day_reports_nothing():
    assert generate_daily_digest(_quiet_day()) == []


def test_day_without_hours_is_empty():
    assert generate_daily_digest(_Day([])) == []
    assert generate_daily_digest(_Day(None)) == []


def test_threshold_crossing_is_reported_with_peak_and_window():
    day = _Day(
        [
            _Hour("10:00", u_v_index=7),
            _Hour("11:00", u_v_index=9),
            _Hour("12:00", u_v_index=10),
            _Hour("13:00", u_v_index=8),
            _Hour("14:00", u_v_index=5),
        ]
    )

    items = generate_daily_digest(day)

    assert len(items) == 1
    uv = items[0]
    assert uv["metric"] == "uv_index"
    assert uv["peak"] == 10
    # only the hours at or above the threshold of 8
    assert uv["from"] == "11:00"
    assert uv["to"] == "13:00"
    assert uv["hours"] == ["11:00", "12:00", "13:00"]


def test_a_below_rule_reports_the_minimum():
    day = _Day([_Hour("03:00", precise_temperature=5.0)])

    items = generate_daily_digest(day)

    assert [i["metric"] for i in items] == ["temperature"]
    assert items[0]["peak"] == 5.0


def test_disabled_rule_is_skipped():
    day = _Day([_Hour("12:00", u_v_index=11)])
    enabled = [r["key"] for r in DAILY_DIGEST_RULES if r["key"] != "uv_index"]

    assert generate_daily_digest(day, enabled=enabled) == []


def test_custom_threshold_widens_the_window():
    day = _Day([_Hour(f"{h:02d}:00", u_v_index=h) for h in range(12)])

    default = generate_daily_digest(day)
    lowered = generate_daily_digest(day, thresholds={"uv_index": 3})

    assert default[0]["from"] == "08:00"
    assert lowered[0]["from"] == "03:00"


def test_missing_values_do_not_trigger_a_rule():
    """IMS omits pm10 and rain chance for some hours."""
    day = _Day([_Hour("12:00", pm10=None, rain_chance=None)])

    assert generate_daily_digest(day) == []


def test_every_rule_has_a_usable_definition():
    for rule in DAILY_DIGEST_RULES:
        assert rule["key"]
        assert rule["label"]
        assert rule["direction"] in ("above", "below")
        assert rule["min"] <= rule["default"] <= rule["max"]
