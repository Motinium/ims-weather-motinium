"""Weather data coordinator for the OpenWeatherMap (OWM) service."""

from __future__ import annotations

import asyncio
import datetime
import logging
from dataclasses import dataclass
from typing import Any

import homeassistant.util.dt as dt_util

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from weatheril import WeatherIL, Forecast, Weather, RadarSatellite, Warning

from .const import (
    DOMAIN,
    IMS_TIMEZONE,
    WARNING_SENSOR_KEYS,
)

_LOGGER = logging.getLogger(__name__)

ATTRIBUTION = "Powered by IMS Weather"

# Use the shared timezone constant
timezone = IMS_TIMEZONE


@dataclass
class WeatherData:
    """Weather data container."""

    current_weather: Weather
    forecast: Forecast
    images: RadarSatellite | None
    warnings: list[Warning]
    sea_warnings: list[Warning]


class WeatherUpdateCoordinator(DataUpdateCoordinator[WeatherData]):
    """Weather data update coordinator."""

    def __init__(
        self,
        city: int | str,
        language: str,
        update_interval: datetime.timedelta,
        hass: Any,
        monitored_conditions: list[str] | None = None,
    ) -> None:
        """Initialize coordinator.

        ``monitored_conditions`` is the list of sensor keys the user has
        enabled for this config entry. When none of them consume
        ``WeatherData.warnings``, the coordinator skips the warnings HTTP
        fetch entirely. ``None`` (the default) means "no conditions were
        stored" and is treated as "all sensors enabled" — the legacy
        behavior in ``sensor.py`` and ``binary_sensor.py`` falls back to
        every description key when conditions are missing.
        """
        self.city = city
        self.language = language
        self.update_interval = update_interval
        self.weather = WeatherIL(str(city), language)

        self._connect_error = False
        self._hass = hass
        self._monitored_conditions: list[str] | None = monitored_conditions

        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=update_interval)

    async def _async_update_data(self) -> WeatherData:
        """Update the data."""
        async with self._hass.timeout.async_timeout(30):
            try:
                _LOGGER.info("Fetching data from IMS")
                data = await self._get_ims_weather()
            except Exception as error:
                raise UpdateFailed(error) from error
        return data

    async def _get_ims_weather(self) -> WeatherData:
        """Poll weather data from IMS."""

        try:
            loop = asyncio.get_event_loop()
        except Exception:
            loop = asyncio.new_event_loop()

        current_weather = await loop.run_in_executor(
            None, self.weather.get_current_analysis
        )
        # weatheril swallows fetch errors and returns None instead of raising;
        # fail the poll with a readable message (the coordinator keeps the
        # previous data and retries) rather than a confusing AttributeError.
        if current_weather is None:
            raise UpdateFailed("IMS current analysis unavailable")

        weather_forecast = await self._fetch_forecast(loop)
        warnings = (
            await self._fetch_warnings(loop) if self._should_fetch_warnings() else []
        )
        sea_warnings = (
            await self._fetch_sea_warnings(loop)
            if self._should_fetch_warnings()
            else []
        )
        # Radar/satellite imagery is not consumed by any entity, so the extra
        # HTTP round-trip is skipped. IMS also serves a 2-byte stub instead of
        # the actual radar PNGs, so there is nothing to render even if it were.
        images = None

        _LOGGER.debug(
            "Data fetched from IMS of %s",
            current_weather.forecast_time.strftime("%m/%d/%Y, %H:%M:%S"),
        )

        self._filter_future_forecast(weather_forecast)
        return WeatherData(
            current_weather, weather_forecast, images, warnings, sea_warnings
        )

    async def _fetch_forecast(self, loop: asyncio.AbstractEventLoop) -> Forecast:
        """Fetch the IMS forecast.

        Non-fatal: ``weatheril`` swallows fetch errors internally and returns
        ``None`` (or an empty ``Forecast``) instead of raising, so an
        exception, a ``None`` result and a forecast without days are all
        treated as failures here. In that case the last successfully fetched
        forecast is reused so a misbehaving forecast endpoint cannot fail the
        whole update while current-weather data is still fresh. On the very
        first refresh there is no previous forecast to fall back on, so the
        failure is propagated and the config entry setup retries as before.
        """
        error: Exception | None = None
        forecast: Forecast | None = None
        try:
            forecast = await loop.run_in_executor(None, self.weather.get_forecast)
        except Exception as err:  # noqa: BLE001 - intentional, see docstring
            error = err
        if forecast is not None and getattr(forecast, "days", None):
            return forecast
        if self.data is not None:
            _LOGGER.warning(
                "Failed to fetch IMS forecast (%s); keeping the last known forecast",
                error if error is not None else "empty response",
            )
            return self.data.forecast
        if error is not None:
            raise error
        raise UpdateFailed("IMS forecast unavailable (weatheril returned no data)")

    async def _fetch_warnings(self, loop: asyncio.AbstractEventLoop) -> list[Warning]:
        """Fetch active IMS weather warnings.

        Non-fatal: returns an empty list on any failure (timeout, network
        error, parse error, server outage) so a misbehaving warnings
        endpoint cannot prevent the rest of the update from completing.
        Downstream consumers (sensor, binary_sensor) handle an empty
        list as "no active warnings".

        Callers should gate this method with ``_should_fetch_warnings()``
        so the HTTP round-trip is avoided entirely when no sensor in the
        current config entry consumes warnings.
        """
        try:
            return await loop.run_in_executor(None, self.weather.get_warnings)
        except Exception as error:  # noqa: BLE001 - intentional, see docstring
            _LOGGER.warning(
                "Failed to fetch IMS weather warnings; continuing with no active warnings: %s",
                error,
            )
            return []

    async def _fetch_sea_warnings(
        self, loop: asyncio.AbstractEventLoop
    ) -> list[Warning]:
        """Fetch active IMS marine warnings.

        Marine alerts are filed against the sea regions, not the (land) region
        of the configured location, so they never appear in ``get_warnings``.
        This reuses the national warnings payload the library already cached,
        so it adds no HTTP round-trip. Non-fatal for the same reasons as
        ``_fetch_warnings``: an empty list simply means "no active alerts".
        """
        try:
            return await loop.run_in_executor(None, self.weather.get_sea_warnings)
        except Exception as error:  # noqa: BLE001 - intentional, see docstring
            _LOGGER.warning(
                "Failed to fetch IMS sea warnings; continuing with none: %s",
                error,
            )
            return []

    def _should_fetch_warnings(self) -> bool:
        """Return True if any enabled sensor consumes ``data.warnings``.

        ``None`` ``monitored_conditions`` falls back to the legacy
        "all sensors enabled" behavior (see ``__init__``). An empty list
        means "no sensors enabled" and yields ``False``.
        """
        conditions = self._monitored_conditions
        if conditions is None:
            return True
        return any(key in WARNING_SENSOR_KEYS for key in conditions)

    @staticmethod
    def _filter_future_forecast(weather_forecast: Forecast) -> None:
        """Filter Forecast to include only future dates"""
        today_datetime = dt_util.as_local(
            datetime.datetime.combine(dt_util.now(timezone).date(), datetime.time())
        )
        filtered_day_list = list(
            filter(lambda daily: daily.date >= today_datetime, weather_forecast.days)
        )

        for daily_forecast in filtered_day_list:
            filtered_hours = []
            for hourly_forecast in daily_forecast.hours:
                forecast_datetime = daily_forecast.date + datetime.timedelta(
                    hours=int(hourly_forecast.hour.split(":")[0])
                )
                if dt_util.now(timezone) <= forecast_datetime:
                    filtered_hours.append(hourly_forecast)
            daily_forecast.hours = filtered_hours

        weather_forecast.days = filtered_day_list
