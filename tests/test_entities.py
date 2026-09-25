"""Tests for the entities: what they make of a parsed IMS forecast, and which
of them an entry gets.

Like the digest tests these import the integration, so they need Home
Assistant and are skipped when it is not installed. The forecast itself comes
from the captured IMS responses through the ``weather`` fixture.
"""

import copy
import types

import pytest
import voluptuous as vol

pytest.importorskip("homeassistant", reason="Home Assistant is not installed")

from conftest import load_fixture
from homeassistant.components.sensor import (
    DEVICE_CLASS_STATE_CLASSES,
    DEVICE_CLASS_UNITS,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from ims_motinium.config_flow import SENSOR_KEYS, known_conditions
from ims_motinium.const import WIND_DIRECTIONS
from ims_motinium.sensor import (
    SENSOR_DESCRIPTIONS,
    SENSOR_DESCRIPTIONS_DICT,
    ImsSensor,
    generate_forecast_extra_state_attributes,
    remove_retired_entities,
    sensor_keys,
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


def _day_sensor(key, coordinator):
    return ImsSensor(coordinator, SENSOR_DESCRIPTIONS_DICT[key])


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


def test_a_day_sensor_whose_day_is_gone_goes_unknown(weather):
    """A sensor past the end of the forecast used to keep its previous day.

    Whenever the forecast came back a day shorter than the poll before -- a
    day that has passed, dropped by the coordinator -- day6 kept showing the
    date that day5 now shows.
    """
    forecast = weather.get_forecast()
    coordinator = _coordinator(forecast)
    day6 = _day_sensor(sensor_keys.TYPE_FORECAST_DAY6, coordinator)
    day6._update_from_latest_data()
    assert day6.native_value is not None

    shorter = copy.copy(forecast)
    shorter.days = forecast.days[1:]
    coordinator.data = types.SimpleNamespace(forecast=shorter, current_weather=None)
    day6._update_from_latest_data()

    assert day6.native_value is None
    assert day6.extra_state_attributes == {}
    assert day6.icon == SENSOR_DESCRIPTIONS_DICT[sensor_keys.TYPE_FORECAST_DAY6].icon


def test_wind_directions_match_the_ims_table():
    """The degrees behind each IMS wind direction id, as IMS publishes them."""
    table = load_fixture("wind_directions.json")["data"]

    for wind_id, entry in table.items():
        assert WIND_DIRECTIONS[int(wind_id)] == float(entry["direction"]), entry["text"]


def _registry_entry(unique_id, entity_id):
    return types.SimpleNamespace(
        domain=entity_id.split(".")[0], unique_id=unique_id, entity_id=entity_id
    )


def test_the_retired_day7_sensor_is_removed_from_the_registry(monkeypatch):
    """IMS sends seven days counting today, so day7 never had one to show.

    Dropping the description alone would leave its registry entry behind as
    an entity "no longer provided", for the user to delete by hand.
    """
    entries = [
        _registry_entry("ims_forecast_day7_35_en", "sensor.ims_forecast_day7"),
        _registry_entry("ims_forecast_day6_35_en", "sensor.ims_forecast_day6"),
        _registry_entry("ims_is_raining_35_en", "binary_sensor.ims_is_raining"),
    ]
    monkeypatch.setattr(
        er, "async_entries_for_config_entry", lambda registry, entry_id: entries
    )
    removed = []

    remove_retired_entities(types.SimpleNamespace(async_remove=removed.append), "x")

    assert removed == ["sensor.ims_forecast_day7"]
    assert "ims_forecast_day7" not in SENSOR_KEYS


def test_the_options_form_still_saves_for_an_entry_that_had_day7():
    """The entry keeps the keys it was saved with, day7 included.

    Offered back unfiltered as the form's default, the stale key failed the
    form's own validation, so the options could not be saved.
    """
    stored = [*SENSOR_KEYS, "ims_forecast_day7"]
    validate = cv.multi_select(SENSOR_KEYS)

    with pytest.raises(vol.Invalid):
        validate(stored)
    assert validate(known_conditions(stored)) == SENSOR_KEYS
    assert known_conditions(None) == SENSOR_KEYS


def test_wind_direction_statistics_average_around_the_circle():
    """As a plain MEASUREMENT the mean of 350° and 10° came out at 180°."""
    description = SENSOR_DESCRIPTIONS_DICT[sensor_keys.TYPE_WIND_DIRECTION]

    assert description.device_class == SensorDeviceClass.WIND_DIRECTION
    assert description.state_class == SensorStateClass.MEASUREMENT_ANGLE


@pytest.mark.parametrize(
    "description",
    [d for d in SENSOR_DESCRIPTIONS if d.device_class is not None],
    ids=lambda d: d.key,
)
def test_each_device_class_gets_a_unit_and_state_class_it_accepts(description):
    """Home Assistant logs a warning for any combination it does not accept."""
    units = DEVICE_CLASS_UNITS.get(description.device_class)
    state_classes = DEVICE_CLASS_STATE_CLASSES.get(description.device_class)

    if units is not None:
        assert description.native_unit_of_measurement in units
    if state_classes is not None and description.state_class is not None:
        assert description.state_class in state_classes
