"""Israel Meteorological Service unofficial python api wrapper"""

import logging
from datetime import datetime

from .consts import (
    CURRENT_ANALYSIS_URL,
    FORECAST_URL,
    IMS_API_URL_BASE,
    RADAR_SATELLITE_URL,
    TIMEZONE,
    WARNINGS_URL,
)
from .forecast import Daily, Forecast, Hourly
from .radar_satellite import RadarSatellite
from .utils import (
    _get_warning_metadata,
    fetch_data,
    get_location_info_by_id,
    get_value,
    warm_warning_caches,
)
from .warning import Warning
from .weather import Weather

logger = logging.getLogger(__name__)

DAILY_KEY = "daily"
HOURLY_KEY = "hourly"
FULL_WARNINGS_DATA_KEY = "full_warnings_data"


DEFAULT_CACHE_EXPIRATION = 30


class WeatherIL:
    def __init__(
        self, location, language="en", cache_expiration_in_sec=DEFAULT_CACHE_EXPIRATION
    ):
        """
        Init the WeatherIL object.
        parameters:
            >>> location: Location Id for the forecast (Table exists in the readme)
            >>> language: can be he (Hebrew) or en (English). default will be "he"
            >>> city_portal_cache_expiration: cache expiration in days for city portal data API. default is 30 seconds
        """
        self._cache_expiration_in_sec = cache_expiration_in_sec
        self.language = language
        self.location = str(location)
        self._analysis_data = None
        self._analysis_last_fetch = None
        self._forecast_data = None
        self._forecast_last_fetch = None
        self._full_warnings_data = None
        self._warnings_last_fetch = None

    def get_current_analysis(self):
        self._get_analysis_data()
        try:
            logger.debug("Getting current analysis")
            analysis_data = self._analysis_data.get(self.location, {})
            if analysis_data:
                logger.debug("Got current analysis for location " + str(self.location))
                # Parse forecast_time and modified_at separately due to datetime parsing
                forecast_time_str = get_value(analysis_data, "forecast_time", None, str)
                forecast_time = (
                    TIMEZONE.localize(
                        datetime.strptime(forecast_time_str, "%Y-%m-%d %H:%M:%S")
                    )
                    if forecast_time_str
                    else None
                )

                modified_at_str = get_value(analysis_data, "modified", None, str)
                modified_at = (
                    TIMEZONE.localize(
                        datetime.strptime(modified_at_str, "%Y-%m-%d %H:%M:%S")
                    )
                    if modified_at_str
                    else None
                )

                return Weather(
                    language=self.language,
                    lid=get_value(analysis_data, "lid", None, str),
                    humidity=get_value(
                        analysis_data, "relative_humidity", None, int, 0
                    ),
                    rain=get_value(analysis_data, "rain", None, float, 0.0, -999.0),
                    rain_chance=get_value(analysis_data, "rain_chance", None, int, 0),
                    temperature=get_value(
                        analysis_data, "temperature", None, float, 0.0
                    ),
                    due_point_temp=get_value(
                        analysis_data, "due_point_Temp", None, int, 0
                    ),
                    wind_speed=get_value(analysis_data, "wind_speed", None, int, 0),
                    wind_chill=get_value(analysis_data, "wind_chill", None, int, 0),
                    wind_direction_id=get_value(
                        analysis_data, "wind_direction_id", None, int, 0
                    ),
                    feels_like=get_value(analysis_data, "feels_like", None, float),
                    heat_stress_level=get_value(
                        analysis_data, "heat_stress_level", None, int, 0
                    ),
                    u_v_index=get_value(analysis_data, "u_v_index", None, int, 0),
                    u_v_level=get_value(analysis_data, "u_v_level", None, str),
                    u_v_i_max=get_value(analysis_data, "u_v_i_max", None, int),
                    u_v_i_factor=get_value(analysis_data, "u_v_i_factor", None, float),
                    wave_height=get_value(
                        analysis_data, "wave_height", None, float, 0.0
                    ),
                    max_temp=get_value(analysis_data, "max_temp", None, int),
                    min_temp=get_value(analysis_data, "min_temp", None, int),
                    pm10=get_value(analysis_data, "pm10", None, int, 0),
                    forecast_time=forecast_time,
                    modified_at=modified_at,
                    json=analysis_data,
                    weather_code=get_value(analysis_data, "weather_code", None, int),
                    gust_speed=get_value(
                        analysis_data, "gust_speed", None, int, None, -999
                    ),
                )
            else:
                # IMS occasionally answers this endpoint with an empty or
                # non-JSON body. The caller turns the None into a failed
                # update and retries, so this is detail, not a failure of its
                # own. Lazy %-formatting: the payload is a dict, and
                # concatenating it onto a string raised TypeError here.
                logger.debug(
                    'No "%s" in current analysis response: %s',
                    self.location,
                    self._analysis_data,
                )
                return None
        except Exception:
            logger.exception("Error getting current analysis")
            return None

    def get_forecast(self):
        """
        Get weather forecast
        return: Forecast object
        """
        logger.debug("Getting forecast")
        self._get_forecast_data()
        try:
            days = []
            forecast_data = self._forecast_data
            logger.debug("Got forecast for location " + str(self.location))
            for key in forecast_data:
                hours = self._get_hourly_forecast(
                    get_value(forecast_data, key, HOURLY_KEY, dict)
                )
                daily = Daily(
                    language=self.language,
                    date=TIMEZONE.localize(datetime.strptime(key, "%Y-%m-%d")),
                    lid=get_value(
                        forecast_data[key], DAILY_KEY, "lid", default_value="0"
                    ),
                    weather_code=get_value(
                        forecast_data[key], DAILY_KEY, "weather_code", int
                    ),
                    minimum_temperature=get_value(
                        forecast_data[key], DAILY_KEY, "minimum_temperature", int
                    ),
                    maximum_temperature=get_value(
                        forecast_data[key], DAILY_KEY, "maximum_temperature", int
                    ),
                    maximum_uvi=get_value(
                        forecast_data[key], DAILY_KEY, "maximum_uvi", int
                    ),
                    u_v_i_factor=get_value(
                        forecast_data[key], "daily", "u_v_i_factor", float
                    ),
                    hours=hours,
                    description=(
                        get_value(
                            forecast_data[key],
                            "country",
                            "description",
                            default_value="",
                        )
                    ).rstrip(),
                )
                days.append(daily)
            return Forecast(days)

        except Exception:
            logger.exception("Error getting forecast data")
            return None

    def _get_hourly_forecast(self, data):
        """
        Get the hourly forecast
        """
        hours = []
        if not data:
            logger.debug("No hourly forecast data for this day")
            return hours
        try:
            for key in data:
                hours.append(  # noqa: PERF401 - multi-line constructor reads better as a loop
                    Hourly(
                        language=self.language,
                        hour=key,
                        forecast_time=TIMEZONE.localize(
                            datetime.strptime(
                                data.get(key, {}).get("forecast_time"),
                                "%Y-%m-%d %H:%M:%S",
                            )
                        ),
                        created=TIMEZONE.localize(
                            datetime.strptime(
                                data.get(key, {}).get("created"), "%Y-%m-%d %H:%M:%S"
                            )
                        ),
                        weather_code=get_value(data, key, "weather_code", int),
                        temperature=get_value(data, key, "temperature", int),
                        precise_temperature=get_value(
                            data, key, "precise_temperature", float
                        ),
                        heat_stress=get_value(data, key, "heat_stress", float),
                        heat_stress_level=get_value(
                            data, key, "heat_stress_level", int
                        ),
                        pm10=get_value(data, key, "pm10", int),
                        relative_humidity=get_value(
                            data, key, "relative_humidity", int
                        ),
                        rain=get_value(data, key, "rain", float, None, -999.0),
                        rain_chance=get_value(data, key, "rain_chance", int),
                        wind_speed=get_value(data, key, "wind_speed", int),
                        gust_speed=get_value(data, key, "gust_speed", int, None, -999),
                        wind_direction_id=get_value(
                            data, key, "wind_direction_id", int
                        ),
                        wave_height=get_value(data, key, "wave_height", float),
                        wind_chill=get_value(data, key, "wind_chill", int),
                        u_v_index=get_value(data, key, "u_v_index", int, None, -8991),
                        u_v_i_max=get_value(data, key, "u_v_i_max", int),
                    )
                )
        except Exception as e:
            # An empty list, not None: Daily.hours is typed as a list and
            # callers iterate it without a None check.
            logger.error("Error getting hourly forecast. " + str(e))
            return []
        return hours

    def _get_images_list(self, data, *keys):
        current = data
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key, {})
            else:
                return []
        return current if isinstance(current, list) else []

    def _append_images(self, rs, image_list, attribute, base_url):
        for item in image_list:
            file_name = item.get("file_name")
            if file_name:
                getattr(rs, attribute).append(base_url + file_name)

    def get_radar_images(self):
        """
        Get the list of images for Satellite and Radar
        return: RadarSatellite objects with the lists
        """
        rs = RadarSatellite()
        try:
            logger.debug("Getting radar images")
            url = RADAR_SATELLITE_URL.format(language=self.language)
            data = fetch_data(url)
            base_url = IMS_API_URL_BASE.format(language="").rstrip("/")

            ims_radar_list = self._get_images_list(data, "data", "types", "IMSRadar")
            self._append_images(rs, ims_radar_list, "imsradar_images", base_url)

            # Only the NATURAL satellite set is collected; IMS also publishes
            # DUST, IR and FOG under the same key if they are ever wanted.
            middle_east_list = self._get_images_list(
                data, "data", "types", "satellite", "NATURAL"
            )
            self._append_images(
                rs, middle_east_list, "middle_east_satellite_images", base_url
            )

            logger.debug(
                f"Got: {len(rs.imsradar_images)} IMS radar images; "
                f"{len(rs.middle_east_satellite_images)} Middle East satellite images"
            )
        except Exception as e:
            logger.error("Error getting images. " + str(e))
        return rs

    def _is_cache_fresh(self, last_fetch):
        """
        Whether data fetched at ``last_fetch`` is still within the cache window.
        """
        if last_fetch is None:
            return False
        age = (datetime.now() - last_fetch).total_seconds()
        return age < self._cache_expiration_in_sec

    def _get_analysis_data(self):
        """
        Get the city current analysis data
        return: dict
        """
        # The timestamp is only moved when data was actually fetched. Touching
        # it on a cache hit would slide the window forward on every call, so a
        # caller polling faster than the expiry would never see fresh data.
        if self._analysis_data and self._is_cache_fresh(self._analysis_last_fetch):
            return

        url = CURRENT_ANALYSIS_URL.format(
            language=self.language, location=self.location
        )
        self._analysis_data = fetch_data(url).get("data", {})
        if self._analysis_data:
            self._analysis_last_fetch = datetime.now()

    def _get_forecast_data(self):
        """
        Get the city forecast data
        """
        if self._forecast_data and self._is_cache_fresh(self._forecast_last_fetch):
            return

        url = FORECAST_URL.format(language=self.language, location=self.location)
        self._forecast_data = fetch_data(url).get("data", {})
        if self._forecast_data:
            self._forecast_last_fetch = datetime.now()

    def _get_warnings_data(self):
        """
        Get the all warning data
        """
        if self._full_warnings_data and self._is_cache_fresh(self._warnings_last_fetch):
            return

        url = WARNINGS_URL.format(language=self.language)
        self._full_warnings_data = fetch_data(url).get("data", {})
        if self._full_warnings_data:
            self._warnings_last_fetch = datetime.now()

    def get_sea_warnings(self):
        """
        Get active warnings for the sea regions (is_sea = 1).

        get_warnings() only returns alerts filed against the region of the
        configured location, which is a land region for any coastal city, so
        marine alerts never show up there. This reuses the already fetched
        (and cached) national warnings payload, so it costs no extra request.
        Alerts covering several sea regions are returned once, keyed by wid.

        return: list of Warning objects
        """
        logger.debug("Getting sea warnings")
        self._get_warnings_data()

        # The /regions endpoint carries no is_sea flag; that lives in the
        # warnings metadata, which is cached after the first call and comes
        # back empty if it could not be read, leaving sea_rids empty too.
        metadata = _get_warning_metadata(self.language)

        sea_rids = [
            rid
            for rid, region in (metadata.get("regions") or {}).items()
            if str(region.get("is_sea")) == "1"
        ]
        logger.debug(f"Sea regions: {sea_rids}")
        return self.get_warnings_for_regions(sea_rids)

    def get_warnings_for_regions(self, region_ids):
        """
        Get active warnings filed against the given regions.

        ``region_ids`` are ids as IMS writes them, e.g. ["r-54", "r-97"]; see
        the ``regions`` map in the warnings metadata. Warnings covering several
        of the requested regions are returned once, keyed by wid. Reuses the
        cached national warnings payload, so it costs no extra request.

        return: list of Warning objects
        """
        self._get_warnings_data()
        return self._collect_warnings(region_ids)

    def _build_warning(self, alert):
        """
        Build one Warning, or None if this alert cannot be parsed.

        One malformed alert -- an unexpected date format, a field IMS
        renamed -- used to raise out of the loop and cost the entire batch.
        The coordinator turns that into "no active warnings", which is the
        one answer a warnings feed must not give wrongly, so a bad alert is
        now dropped on its own.
        """
        try:
            return Warning(
                language=self.language,
                location_id=int(self.location),
                wid=int(alert["wid"]),
                alert_id=int(alert["alert_id"]),
                severity_id=int(alert["severity_id"]),
                warning_type_id=int(alert["warning_type_id"]),
                sent=alert["sent"],
                valid_from=alert["valid_from"],
                valid_to=alert["valid_to"],
                full_en=alert["full_en"],
                full_he=alert["full_he"],
                text=alert["text"],
                text_full=alert["text_full"],
                valid_from_unix=int(alert["valid_from_unix"]),
                groups=alert["groups"],
                regions=alert["regions"],
            )
        except Exception as e:
            logger.warning(
                "Skipping an IMS warning that did not parse (wid %s): %s",
                alert.get("wid") if isinstance(alert, dict) else alert,
                e,
            )
            return None

    def _collect_warnings(self, region_ids):
        """
        Build Warning objects for the given region ids, de-duplicated by wid.
        """
        if not self._full_warnings_data:
            return []

        # Warning resolves its severity, type, group and region names as it
        # is constructed, and those lookups are lazy. Loading them here means
        # the network call the whole batch depends on happens once, in the
        # open, rather than from inside whichever alert happens to be first.
        warm_warning_caches(self.language)

        warnings = {}
        for key in self._full_warnings_data.get(FULL_WARNINGS_DATA_KEY) or {}:
            daily_warnings: dict = get_value(
                self._full_warnings_data, FULL_WARNINGS_DATA_KEY, key, dict
            )
            for region_id in region_ids:
                for alert in daily_warnings.get(region_id, {}).values():
                    warning = self._build_warning(alert)
                    if warning is not None and warning.wid not in warnings:
                        warnings[warning.wid] = warning
        return list(warnings.values())

    def get_warnings(self):
        """
        Get active warnings for the region the configured location sits in.

        Goes through the same collector as the other two, so an alert filed
        under several dates is returned once rather than once per date, and
        an unknown location gives an empty list instead of raising into the
        caller.

        return: list of Warning objects
        """
        logger.debug("Getting warnings")

        location_info = get_location_info_by_id(self.language, self.location)
        rid = location_info.get("rid") if location_info else None
        if not rid:
            logger.warning(
                "No region known for location %s; cannot select its warnings",
                self.location,
            )
            return []

        return self.get_warnings_for_regions(["r-" + str(rid)])
