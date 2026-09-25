"""Tests for what the entities make of a parsed IMS forecast.

Like the digest tests these import the integration, so they need Home
Assistant and are skipped when it is not installed. The forecast itself comes
from the captured IMS responses through the ``weather`` fixture.
"""

import types

import pytest

pytest.importorskip("homeassistant", reason="Home Assistant is not installed")

from ims_motinium.sensor import (
    generate_forecast_extra_state_attributes,
)
from ims_motinium.weather import IMSWeather

# Clear sky. IMS has one code for it day and night; the night look is derived.
CLEAR = 1250


def _coordinator(forecast, current_weather=None):
    """Just enough of WeatherUpdateCoordinator for an entity to read from."""
    return types.SimpleNamespace(
        city="35",
        language="en",
        data=types.SimpleNamespace(forecast=forecast, current_weather=current_weather),
    )


def _weather_entity(coordinator):
    return IMSWeather("IMS", "35", "hourly", coordinator, "Tel Aviv - Yafo", "No")


def test_hourly_rain_chance_is_already_a_percentage(weather):
    """IMS sends "30" for 30%, which the sensors and the digest read as is.

    The weather entity multiplied it by 100 again and reported 3000%.
    """
    forecast = weather.get_forecast()
    hour = forecast.days[1].hours[12]
    hour.rain_chance = 30

    entity = _weather_entity(_coordinator(forecast))
    by_time = {item["datetime"]: item for item in entity._forecast(hourly=True)}

    assert by_time[hour.forecast_time.isoformat()]["precipitation_probability"] == 30


def test_a_clear_hour_at_night_gets_the_night_icon(weather):
    """weatheril parses weather codes as int; the night table is keyed by str.

    Comparing the two never matched, so a clear 23:00 was drawn as a sun. The
    night names it would have reached were not MDI icons either
    (mdi:clear-night, mdi:weather-partly-cloudy-night), so fixing only the
    comparison would have drawn nothing at all.
    """
    day = weather.get_forecast().days[1]
    for hour in day.hours:
        hour.weather_code = CLEAR

    attributes = generate_forecast_extra_state_attributes(day)

    assert attributes["23:00"]["weather"]["icon"] == "mdi:weather-night"
    assert attributes["12:00"]["weather"]["icon"] == "mdi:weather-sunny"


def test_the_weather_entity_reports_a_clear_night(weather):
    current = weather.get_current_analysis()
    current.weather_code = CLEAR
    current.json["forecast_time"] = "2026-07-24 23:20:00"
    forecast = weather.get_forecast()
    for day in forecast.days:
        for hour in day.hours:
            hour.weather_code = CLEAR

    entity = _weather_entity(_coordinator(forecast, current))
    by_time = {item["datetime"]: item for item in entity._forecast(hourly=True)}
    night = forecast.days[1].hours[23].forecast_time.isoformat()
    noon = forecast.days[1].hours[12].forecast_time.isoformat()

    assert entity.condition == "clear-night"
    assert by_time[night]["condition"] == "clear-night"
    assert by_time[noon]["condition"] == "sunny"
