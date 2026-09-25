"""Tests for what the entities make of a parsed IMS forecast.

Like the digest tests these import the integration, so they need Home
Assistant and are skipped when it is not installed. The forecast itself comes
from the captured IMS responses through the ``weather`` fixture.
"""

import types

import pytest

pytest.importorskip("homeassistant", reason="Home Assistant is not installed")

from ims_motinium.weather import IMSWeather


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
