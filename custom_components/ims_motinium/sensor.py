from typing import Any
import logging
import types

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    CONF_MONITORED_CONDITIONS,
    DEGREE,
    PERCENTAGE,
    UV_INDEX,
    EntityCategory,
    UnitOfPrecipitationDepth,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ImsEntity, ImsSensorEntityDescription
from .weather_update_coordinator import WeatherData
from .const import (
    DOMAIN,
    ENTRY_WEATHER_COORDINATOR,
    FIELD_NAME_DEW_POINT_TEMP,
    FIELD_NAME_FEELS_LIKE,
    FIELD_NAME_FORECAST_TIME,
    FIELD_NAME_HUMIDITY,
    FIELD_NAME_GUST_SPEED,
    FIELD_NAME_LAST_MODIFIED,
    FIELD_NAME_LOCATION,
    FIELD_NAME_PM10,
    FIELD_NAME_RAIN,
    FIELD_NAME_RAIN_CHANCE,
    FIELD_NAME_TEMPERATURE,
    FIELD_NAME_UV_INDEX,
    FIELD_NAME_UV_INDEX_MAX,
    FIELD_NAME_UV_LEVEL,
    FIELD_NAME_WIND_DIRECTION_ID,
    FIELD_NAME_WIND_SPEED,
    FORECAST_MODE,
    IMS_PLATFORM,
    IMS_PLATFORMS,
    IMS_SENSOR_KEY_PREFIX,
    TYPE_CITY,
    TYPE_CURRENT_UV_INDEX,
    TYPE_CURRENT_UV_LEVEL,
    TYPE_DEW_POINT_TEMP,
    TYPE_FEELS_LIKE,
    TYPE_FORECAST_DAY1,
    TYPE_FORECAST_DAY2,
    TYPE_FORECAST_DAY3,
    TYPE_FORECAST_DAY4,
    TYPE_FORECAST_DAY5,
    TYPE_FORECAST_DAY6,
    TYPE_FORECAST_DAY7,
    TYPE_FORECAST_PREFIX,
    TYPE_FORECAST_TIME,
    TYPE_FORECAST_TODAY,
    TYPE_GUST_SPEED,
    TYPE_HUMIDITY,
    TYPE_LAST_MODIFIED,
    TYPE_MAX_UV_INDEX,
    TYPE_PM10,
    TYPE_PRECIPITATION,
    TYPE_PRECIPITATION_PROBABILITY,
    TYPE_TEMPERATURE,
    TYPE_WIND_DIRECTION,
    TYPE_WIND_SPEED,
    UV_LEVEL_EXTREME,
    UV_LEVEL_HIGH,
    UV_LEVEL_LOW,
    UV_LEVEL_MODERATE,
    UV_LEVEL_VHIGH,
    WEATHER_CODE_TO_ICON,
    WIND_DIRECTIONS,
    FIELD_NAME_WARNING,
    TYPE_WEATHER_WARNINGS,
    TYPE_SEA_WARNINGS,
    WARNING_SEVERITY_COLORS,
    DATETIME_FORMAT,
)
from .utils import get_hourly_weather_icon

sensor_keys = types.SimpleNamespace()
sensor_keys.TYPE_CURRENT_UV_INDEX = IMS_SENSOR_KEY_PREFIX + TYPE_CURRENT_UV_INDEX
sensor_keys.TYPE_CURRENT_UV_LEVEL = IMS_SENSOR_KEY_PREFIX + TYPE_CURRENT_UV_LEVEL
sensor_keys.TYPE_DEW_POINT_TEMP = IMS_SENSOR_KEY_PREFIX + TYPE_DEW_POINT_TEMP
sensor_keys.TYPE_MAX_UV_INDEX = IMS_SENSOR_KEY_PREFIX + TYPE_MAX_UV_INDEX
sensor_keys.TYPE_GUST_SPEED = IMS_SENSOR_KEY_PREFIX + TYPE_GUST_SPEED
sensor_keys.TYPE_CITY = IMS_SENSOR_KEY_PREFIX + TYPE_CITY
sensor_keys.TYPE_TEMPERATURE = IMS_SENSOR_KEY_PREFIX + TYPE_TEMPERATURE
sensor_keys.TYPE_HUMIDITY = IMS_SENSOR_KEY_PREFIX + TYPE_HUMIDITY
sensor_keys.TYPE_FORECAST_TIME = IMS_SENSOR_KEY_PREFIX + TYPE_FORECAST_TIME
sensor_keys.TYPE_LAST_MODIFIED = IMS_SENSOR_KEY_PREFIX + TYPE_LAST_MODIFIED
sensor_keys.TYPE_FEELS_LIKE = IMS_SENSOR_KEY_PREFIX + TYPE_FEELS_LIKE
sensor_keys.TYPE_PM10 = IMS_SENSOR_KEY_PREFIX + TYPE_PM10
sensor_keys.TYPE_PRECIPITATION = IMS_SENSOR_KEY_PREFIX + TYPE_PRECIPITATION
sensor_keys.TYPE_PRECIPITATION_PROBABILITY = (
    IMS_SENSOR_KEY_PREFIX + TYPE_PRECIPITATION_PROBABILITY
)
sensor_keys.TYPE_WIND_DIRECTION = IMS_SENSOR_KEY_PREFIX + TYPE_WIND_DIRECTION
sensor_keys.TYPE_WEATHER_WARNINGS = IMS_SENSOR_KEY_PREFIX + TYPE_WEATHER_WARNINGS
sensor_keys.TYPE_SEA_WARNINGS = IMS_SENSOR_KEY_PREFIX + TYPE_SEA_WARNINGS
sensor_keys.TYPE_WIND_SPEED = IMS_SENSOR_KEY_PREFIX + TYPE_WIND_SPEED
sensor_keys.TYPE_FORECAST_TODAY = (
    IMS_SENSOR_KEY_PREFIX + TYPE_FORECAST_PREFIX + TYPE_FORECAST_TODAY
)
sensor_keys.TYPE_FORECAST_DAY1 = (
    IMS_SENSOR_KEY_PREFIX + TYPE_FORECAST_PREFIX + TYPE_FORECAST_DAY1
)
sensor_keys.TYPE_FORECAST_DAY2 = (
    IMS_SENSOR_KEY_PREFIX + TYPE_FORECAST_PREFIX + TYPE_FORECAST_DAY2
)
sensor_keys.TYPE_FORECAST_DAY3 = (
    IMS_SENSOR_KEY_PREFIX + TYPE_FORECAST_PREFIX + TYPE_FORECAST_DAY3
)
sensor_keys.TYPE_FORECAST_DAY4 = (
    IMS_SENSOR_KEY_PREFIX + TYPE_FORECAST_PREFIX + TYPE_FORECAST_DAY4
)
sensor_keys.TYPE_FORECAST_DAY5 = (
    IMS_SENSOR_KEY_PREFIX + TYPE_FORECAST_PREFIX + TYPE_FORECAST_DAY5
)
sensor_keys.TYPE_FORECAST_DAY6 = (
    IMS_SENSOR_KEY_PREFIX + TYPE_FORECAST_PREFIX + TYPE_FORECAST_DAY6
)
sensor_keys.TYPE_FORECAST_DAY7 = (
    IMS_SENSOR_KEY_PREFIX + TYPE_FORECAST_PREFIX + TYPE_FORECAST_DAY7
)

_LOGGER = logging.getLogger(__name__)

# Units for the plain hourly values in the forecast attributes. Declared once
# per sensor instead of repeating a {value, unit} pair on every hour.
HOURLY_UNITS = {
    "temperature": UnitOfTemperature.CELSIUS,
    "humidity": PERCENTAGE,
    "rain": UnitOfPrecipitationDepth.MILLIMETERS,
    "rain_chance": PERCENTAGE,
    "wind_speed": UnitOfSpeed.KILOMETERS_PER_HOUR,
    "wind_direction": DEGREE,
    "gust_speed": UnitOfSpeed.KILOMETERS_PER_HOUR,
    "wind_chill": UnitOfTemperature.CELSIUS,
    "heat_stress": UnitOfTemperature.CELSIUS,
    "uv_index": UV_INDEX,
    "uv_index_max": UV_INDEX,
    "pm10": CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    "wave_height": "m",
}

SENSOR_DESCRIPTIONS: list[ImsSensorEntityDescription] = [
    ImsSensorEntityDescription(
        key=IMS_SENSOR_KEY_PREFIX + TYPE_CURRENT_UV_INDEX,
        name="IMS Current UV Index",
        icon="mdi:weather-sunny",
        native_unit_of_measurement=UV_INDEX,
        state_class=SensorStateClass.MEASUREMENT,
        forecast_mode=FORECAST_MODE.CURRENT,
        field_name=FIELD_NAME_UV_INDEX,
    ),
    ImsSensorEntityDescription(
        key=IMS_SENSOR_KEY_PREFIX + TYPE_CURRENT_UV_LEVEL,
        name="IMS Current UV Level",
        icon="mdi:weather-sunny",
        forecast_mode=FORECAST_MODE.CURRENT,
        field_name=FIELD_NAME_UV_LEVEL,
    ),
    ImsSensorEntityDescription(
        key=IMS_SENSOR_KEY_PREFIX + TYPE_MAX_UV_INDEX,
        name="IMS Max UV Index",
        icon="mdi:weather-sunny",
        native_unit_of_measurement=UV_INDEX,
        state_class=SensorStateClass.MEASUREMENT,
        forecast_mode=FORECAST_MODE.CURRENT,
        field_name=FIELD_NAME_UV_INDEX_MAX,
    ),
    ImsSensorEntityDescription(
        key=IMS_SENSOR_KEY_PREFIX + TYPE_CITY,
        name="IMS City",
        icon="mdi:city",
        forecast_mode=FORECAST_MODE.CURRENT,
        field_name=FIELD_NAME_LOCATION,
    ),
    ImsSensorEntityDescription(
        key=IMS_SENSOR_KEY_PREFIX + TYPE_TEMPERATURE,
        name="IMS Temperature",
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        forecast_mode=FORECAST_MODE.CURRENT,
        field_name=FIELD_NAME_TEMPERATURE,
    ),
    ImsSensorEntityDescription(
        key=IMS_SENSOR_KEY_PREFIX + TYPE_FEELS_LIKE,
        name="IMS Feels Like",
        icon="mdi:water-percent",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        forecast_mode=FORECAST_MODE.CURRENT,
        field_name=FIELD_NAME_FEELS_LIKE,
    ),
    ImsSensorEntityDescription(
        key=IMS_SENSOR_KEY_PREFIX + TYPE_HUMIDITY,
        name="IMS Humidity",
        icon="mdi:weather-sunny",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        forecast_mode=FORECAST_MODE.CURRENT,
        field_name=FIELD_NAME_HUMIDITY,
    ),
    ImsSensorEntityDescription(
        key=IMS_SENSOR_KEY_PREFIX + TYPE_WIND_DIRECTION,
        name="IMS Wind Direction",
        icon="mdi:weather-windy",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        forecast_mode=FORECAST_MODE.CURRENT,
        field_name=FIELD_NAME_WIND_DIRECTION_ID,
    ),
    ImsSensorEntityDescription(
        key=IMS_SENSOR_KEY_PREFIX + TYPE_WIND_SPEED,
        name="IMS Wind Speed",
        icon="mdi:weather-windy",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        forecast_mode=FORECAST_MODE.CURRENT,
        field_name=FIELD_NAME_WIND_SPEED,
    ),
    ImsSensorEntityDescription(
        key=IMS_SENSOR_KEY_PREFIX + TYPE_GUST_SPEED,
        name="IMS Gust Speed",
        icon="mdi:weather-dust",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        forecast_mode=FORECAST_MODE.CURRENT,
        field_name=FIELD_NAME_GUST_SPEED,
    ),
    ImsSensorEntityDescription(
        key=IMS_SENSOR_KEY_PREFIX + TYPE_FORECAST_TIME,
        name="IMS Forecast Time",
        icon="mdi:calendar-clock",
        device_class=SensorDeviceClass.TIMESTAMP,
        forecast_mode=FORECAST_MODE.CURRENT,
        field_name=FIELD_NAME_FORECAST_TIME,
    ),
    ImsSensorEntityDescription(
        # When IMS last recomputed the model run behind the current analysis.
        # Distinct from forecast_time (which slot a value belongs to): IMS
        # precomputes slots hours ahead, so a stalled model pipeline keeps
        # serving advancing slots while this timestamp stops moving.
        key=IMS_SENSOR_KEY_PREFIX + TYPE_LAST_MODIFIED,
        name="IMS Last Modified",
        icon="mdi:database-clock",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        forecast_mode=FORECAST_MODE.CURRENT,
        field_name=FIELD_NAME_LAST_MODIFIED,
    ),
    ImsSensorEntityDescription(
        key=IMS_SENSOR_KEY_PREFIX + TYPE_PRECIPITATION,
        name="IMS Precipitation",
        icon="mdi:weather-pouring",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.MEASUREMENT,
        forecast_mode=FORECAST_MODE.CURRENT,
        field_name=FIELD_NAME_RAIN,
    ),
    ImsSensorEntityDescription(
        key=IMS_SENSOR_KEY_PREFIX + TYPE_PRECIPITATION_PROBABILITY,
        name="IMS Precipitation Probability",
        icon="mdi:cloud-percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        forecast_mode=FORECAST_MODE.CURRENT,
        field_name=FIELD_NAME_RAIN_CHANCE,
    ),
    ImsSensorEntityDescription(
        key=IMS_SENSOR_KEY_PREFIX + TYPE_PM10,
        name="IMS PM10",
        icon="mdi:air-filter",
        device_class=SensorDeviceClass.PM10,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        forecast_mode=FORECAST_MODE.CURRENT,
        field_name=FIELD_NAME_PM10,
    ),
    ImsSensorEntityDescription(
        key=IMS_SENSOR_KEY_PREFIX + TYPE_DEW_POINT_TEMP,
        name="IMS Dew Point",
        icon="mdi:water-circle",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        forecast_mode=FORECAST_MODE.CURRENT,
        field_name=FIELD_NAME_DEW_POINT_TEMP,
    ),
    ImsSensorEntityDescription(
        key=IMS_SENSOR_KEY_PREFIX + TYPE_WEATHER_WARNINGS,
        name="IMS Weather Warnings",
        icon="mdi:weather-cloudy-alert",
        forecast_mode=FORECAST_MODE.CURRENT,
        field_name=FIELD_NAME_WARNING,
    ),
    ImsSensorEntityDescription(
        # Marine alerts are filed against the sea regions, so they never show
        # up in the location's own warnings (a coastal city sits in a land
        # region). Sea state, swimming danger, high waves.
        key=IMS_SENSOR_KEY_PREFIX + TYPE_SEA_WARNINGS,
        name="IMS Sea Warnings",
        icon="mdi:waves-arrow-up",
        forecast_mode=FORECAST_MODE.CURRENT,
        field_name=FIELD_NAME_WARNING,
    ),
    ImsSensorEntityDescription(
        key=IMS_SENSOR_KEY_PREFIX + TYPE_FORECAST_PREFIX + TYPE_FORECAST_TODAY,
        name="IMS Forecast Today",
        icon="mdi:weather-sunny",
    ),
    ImsSensorEntityDescription(
        key=IMS_SENSOR_KEY_PREFIX + TYPE_FORECAST_PREFIX + TYPE_FORECAST_DAY1,
        name="IMS Forecast Day1",
        icon="mdi:weather-sunny",
    ),
    ImsSensorEntityDescription(
        key=IMS_SENSOR_KEY_PREFIX + TYPE_FORECAST_PREFIX + TYPE_FORECAST_DAY2,
        name="IMS Forecast Day2",
        icon="mdi:weather-windy",
    ),
    ImsSensorEntityDescription(
        key=IMS_SENSOR_KEY_PREFIX + TYPE_FORECAST_PREFIX + TYPE_FORECAST_DAY3,
        name="IMS Forecast Day3",
        icon="mdi:weather-sunny",
    ),
    ImsSensorEntityDescription(
        key=IMS_SENSOR_KEY_PREFIX + TYPE_FORECAST_PREFIX + TYPE_FORECAST_DAY4,
        name="IMS Forecast Day4",
        icon="mdi:weather-sunny",
    ),
    ImsSensorEntityDescription(
        key=IMS_SENSOR_KEY_PREFIX + TYPE_FORECAST_PREFIX + TYPE_FORECAST_DAY5,
        name="IMS Forecast Day5",
        icon="mdi:weather-sunny",
    ),
    ImsSensorEntityDescription(
        key=IMS_SENSOR_KEY_PREFIX + TYPE_FORECAST_PREFIX + TYPE_FORECAST_DAY6,
        name="IMS Forecast Day6",
        icon="mdi:weather-sunny",
    ),
    ImsSensorEntityDescription(
        key=IMS_SENSOR_KEY_PREFIX + TYPE_FORECAST_PREFIX + TYPE_FORECAST_DAY7,
        name="IMS Forecast Day7",
        icon="mdi:weather-sunny",
    ),
]

SENSOR_DESCRIPTIONS_DICT = {desc.key: desc for desc in SENSOR_DESCRIPTIONS}
SENSOR_DESCRIPTIONS_KEYS = [desc.key for desc in SENSOR_DESCRIPTIONS]

weather = None


async def async_setup_platform(
    hass, config_entry, async_add_entities, discovery_info=None
):
    _LOGGER.warning(
        "Configuration of IMS Weather sensor in YAML is deprecated "
        "Your existing configuration has been imported into the UI automatically "
        "and can be safely removed from your configuration.yaml file"
    )

    # Define as a sensor platform
    config_entry[IMS_PLATFORM] = [IMS_PLATFORMS[0]]

    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_IMPORT}, data=config_entry
        )
    )


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up IMS Weather sensor entities based on a config entry."""

    domain_data = hass.data[DOMAIN][config_entry.entry_id]
    conditions = domain_data[CONF_MONITORED_CONDITIONS]
    weather_coordinator = domain_data[ENTRY_WEATHER_COORDINATOR]

    # Add IMS Sensors
    sensors: list[ImsSensor] = []

    if conditions is None:
        # If a problem happens - create all sensors
        conditions = SENSOR_DESCRIPTIONS_KEYS

    for condition in conditions:
        if condition in SENSOR_DESCRIPTIONS_KEYS:
            description = SENSOR_DESCRIPTIONS_DICT[condition]
            sensors.append(ImsSensor(weather_coordinator, description))

    async_add_entities(sensors, update_before_add=True)


def generate_single_warning_string(warning):
    return f"{warning.valid_from.strftime(DATETIME_FORMAT)} - {warning.valid_to.strftime(DATETIME_FORMAT)}\n{warning.text_full}"


def generate_single_warning_detail(warning):
    """Structured view of one warning for template/card use.

    Surfaces the fields ``weatheril`` already parses (severity, warning type,
    covered regions, audience groups) that the plain ``warnings`` string list
    drops, so a Lovelace card can style, label and filter warnings without
    guessing any of it from the free text. ``getattr`` guards keep it working
    across weatheril versions that may not expose every field.
    """
    severity = getattr(warning, "severity", None) or ""
    sent = getattr(warning, "sent", None)
    return {
        "severity": severity or None,
        # IMS's own colour for the level, so cards match the IMS site.
        "severity_color": next(
            (
                color
                for name, color in WARNING_SEVERITY_COLORS.items()
                if name in severity.lower()
            ),
            None,
        ),
        "type": getattr(warning, "warning_type", None),
        "region": getattr(warning, "region_name", None),
        "regions": getattr(warning, "regions", None),
        # Audience, e.g. "General Public", "Seamanship", "Aviation" —
        # lets a card show or hide alerts that are not meant for you.
        "groups": sorted(set(getattr(warning, "groups", None) or [])),
        # Stable id: the same alert is filed against several regions.
        "id": getattr(warning, "wid", None),
        "sent": sent.isoformat() if sent else None,
        "valid_from": warning.valid_from.isoformat(),
        "valid_to": warning.valid_to.isoformat(),
        "text": warning.text_full,
    }


def generate_warnings_extra_state_attributes(warnings):
    # ``warnings`` (list of strings) is kept for backward compatibility;
    # ``warnings_data`` adds the structured fields for richer cards.
    attributes = {
        "warnings": [generate_single_warning_string(w) for w in warnings],
        "warnings_data": [generate_single_warning_detail(w) for w in warnings],
    }
    return attributes


def generate_forecast_extra_state_attributes(daily_forecast):
    attributes = {
        "minimum_temperature": {
            "value": daily_forecast.minimum_temperature,
            "unit": UnitOfTemperature.CELSIUS,
        },
        "maximum_temperature": {
            "value": daily_forecast.maximum_temperature,
            "unit": UnitOfTemperature.CELSIUS,
        },
        "maximum_uvi": {"value": daily_forecast.maximum_uvi, "unit": UV_INDEX},
        "weather": {
            "value": daily_forecast.weather,
            "icon": WEATHER_CODE_TO_ICON.get(
                str(daily_forecast.weather_code), "mdi:weather-sunny"
            ),
        },
        "description": {"value": daily_forecast.description},
        "date": {"value": daily_forecast.date.strftime("%Y/%m/%d")},
    }

    # When IMS computed this forecast run. Only the hourly entries carry it,
    # so take the first available one; it is the same across the run.
    forecast_created = next(
        (hour.created for hour in daily_forecast.hours if getattr(hour, "created", None)),
        None,
    )
    if forecast_created:
        attributes["created"] = {"value": forecast_created.isoformat()}

    last_weather_code = None
    last_weather_status = None
    for hour in daily_forecast.hours:
        if hour.weather and hour.weather != "Nothing":
            last_weather_status = hour.weather
        elif not last_weather_status:
            last_weather_status = daily_forecast.weather

        if hour.weather_code and hour.weather_code != "0":
            last_weather_code = hour.weather_code
        elif not last_weather_code:
            last_weather_code = daily_forecast.weather_code

        hourly_weather_code = get_hourly_weather_icon(hour.hour, last_weather_code)

        hourly = {
            "weather": {
                "value": last_weather_status,
                "icon": WEATHER_CODE_TO_ICON.get(str(hourly_weather_code)),
            },
            "temperature": {
                "value": hour.precise_temperature or hour.temperature,
                "unit": UnitOfTemperature.CELSIUS,
            },
        }
        # The remaining hourly fields weatheril parses. Kept as plain values
        # (units are declared once in HOURLY_UNITS) because the nested
        # {value, unit} form roughly triples the size of a 24-hour day, and
        # these attributes are written to the recorder on every poll.
        for name, value in (
            ("humidity", hour.relative_humidity),
            ("rain", hour.rain),
            ("rain_chance", hour.rain_chance),
            ("wind_speed", hour.wind_speed),
            ("wind_direction", hour.wind_direction),
            ("gust_speed", hour.gust_speed),
            ("wind_chill", hour.wind_chill),
            ("heat_stress", hour.heat_stress),
            ("heat_stress_level", hour.heat_stress_level),
            ("uv_index", hour.u_v_index),
            ("uv_index_max", hour.u_v_i_max),
            ("pm10", hour.pm10),
            ("wave_height", hour.wave_height),
        ):
            if value is not None:
                hourly[name] = value

        attributes[hour.hour] = hourly

    attributes["hourly_units"] = HOURLY_UNITS

    return attributes


class ImsSensor(ImsEntity, SensorEntity):
    """Representation of an IMS sensor."""

    entity_description: ImsSensorEntityDescription
    _attr_native_value: Any

    @callback
    def _update_from_latest_data(self) -> None:
        """Update the state."""
        data: WeatherData | None = self.coordinator.data

        if (
            self.entity_description.forecast_mode == FORECAST_MODE.DAILY
            or self.entity_description.forecast_mode == FORECAST_MODE.HOURLY
        ):
            if not data or not data.forecast:
                _LOGGER.warning(
                    "For %s - no data.forecast", self.entity_description.key
                )
                self._attr_native_value = None
                return
        elif self.entity_description.forecast_mode == FORECAST_MODE.CURRENT:
            if not data or not data.current_weather:
                _LOGGER.warning(
                    "For %s - no data.current_weather", self.entity_description.key
                )
                self._attr_native_value = None
                return

        # After these checks, data is guaranteed to be not None
        assert data is not None

        match self.entity_description.key:
            case sensor_keys.TYPE_CURRENT_UV_LEVEL:
                match data.current_weather.u_v_level:
                    case "E":
                        self._attr_native_value = UV_LEVEL_EXTREME
                    case "V":
                        self._attr_native_value = UV_LEVEL_VHIGH
                    case "H":
                        self._attr_native_value = UV_LEVEL_HIGH
                    case "M":
                        self._attr_native_value = UV_LEVEL_MODERATE
                    case _:
                        self._attr_native_value = UV_LEVEL_LOW

            case sensor_keys.TYPE_CURRENT_UV_INDEX:
                self._attr_native_value = data.current_weather.u_v_index

            case sensor_keys.TYPE_MAX_UV_INDEX:
                self._attr_native_value = data.current_weather.u_v_i_max

            case sensor_keys.TYPE_GUST_SPEED:
                self._attr_native_value = data.current_weather.gust_speed

            case sensor_keys.TYPE_CITY:
                _LOGGER.debug(
                    "Location: %s, entity: %s",
                    data.current_weather.location,
                    self.entity_description.key,
                )
                self._attr_native_value = data.current_weather.location

            case sensor_keys.TYPE_TEMPERATURE:
                self._attr_native_value = data.current_weather.temperature

            case sensor_keys.TYPE_DEW_POINT_TEMP:
                self._attr_native_value = data.current_weather.due_point_temp

            case sensor_keys.TYPE_FEELS_LIKE:
                self._attr_native_value = data.current_weather.feels_like

            case sensor_keys.TYPE_HUMIDITY:
                self._attr_native_value = data.current_weather.humidity

            case sensor_keys.TYPE_PM10:
                self._attr_native_value = data.current_weather.pm10

            case sensor_keys.TYPE_PRECIPITATION:
                self._attr_native_value = (
                    data.current_weather.rain
                    if (data.current_weather.rain and data.current_weather.rain > 0.0)
                    else 0.0
                )

            case sensor_keys.TYPE_PRECIPITATION_PROBABILITY:
                self._attr_native_value = data.current_weather.rain_chance

            case sensor_keys.TYPE_FORECAST_TIME:
                self._attr_native_value = (
                    data.current_weather.forecast_time.astimezone()
                )

            case sensor_keys.TYPE_LAST_MODIFIED:
                # weatheril leaves modified_at as None when IMS omits the field
                modified_at = getattr(data.current_weather, "modified_at", None)
                self._attr_native_value = (
                    modified_at.astimezone() if modified_at else None
                )

            case sensor_keys.TYPE_WIND_DIRECTION:
                self._attr_native_value = WIND_DIRECTIONS[
                    int(data.current_weather.wind_direction_id)
                ]

            case sensor_keys.TYPE_WIND_SPEED:
                self._attr_native_value = data.current_weather.wind_speed

            case sensor_keys.TYPE_WEATHER_WARNINGS:
                self._attr_native_value = len(data.warnings)
                self._attr_extra_state_attributes = (
                    generate_warnings_extra_state_attributes(data.warnings)
                )

            case sensor_keys.TYPE_SEA_WARNINGS:
                sea_warnings = getattr(data, "sea_warnings", None) or []
                self._attr_native_value = len(sea_warnings)
                self._attr_extra_state_attributes = (
                    generate_warnings_extra_state_attributes(sea_warnings)
                )

            case (
                sensor_keys.TYPE_FORECAST_TODAY
                | sensor_keys.TYPE_FORECAST_DAY1
                | sensor_keys.TYPE_FORECAST_DAY2
                | sensor_keys.TYPE_FORECAST_DAY3
                | sensor_keys.TYPE_FORECAST_DAY4
                | sensor_keys.TYPE_FORECAST_DAY5
                | sensor_keys.TYPE_FORECAST_DAY6
                | sensor_keys.TYPE_FORECAST_DAY7
            ):
                day_index = (
                    0
                    if self.entity_description.key == sensor_keys.TYPE_FORECAST_TODAY
                    else int(self.entity_description.key[-1])
                )
                if day_index < len(data.forecast.days):
                    daily_forecast = data.forecast.days[day_index]
                    self._attr_native_value = daily_forecast.day
                    self._attr_extra_state_attributes = (
                        generate_forecast_extra_state_attributes(daily_forecast)
                    )
                    self._attr_icon = WEATHER_CODE_TO_ICON.get(
                        str(daily_forecast.weather_code), "mdi:weather-sunny"
                    )

            case _:
                self._attr_native_value = None
