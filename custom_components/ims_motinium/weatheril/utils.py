import json
import logging
import threading
from datetime import datetime

import requests

from .consts import (
    EN_LOCATIONS,
    EN_WEATHER_CODES,
    EN_WIND_DIRECTIONS,
    LOCATIONS_INFO_URL,
    REGIONS_URL,
    WARNINGS_METADTA_URL,
    WEATHER_CODES_URL,
    WIND_DIRECTIONS_URL,
)

logger = logging.getLogger(__name__)

# One session for every request: IMS is a single host, so reusing the
# connection avoids a TCP and TLS handshake per call.
_session = requests.Session()

# The lookup tables below are fetched once and then reused for the lifetime of
# the process. Home Assistant calls this library from executor threads, so the
# lazy population is guarded to keep two threads from fetching at the same time
# and overwriting each other.
_cache_lock = threading.RLock()

_weather_code_map: dict = {}
_locations_map: dict = {}
_wind_direction_map: dict = {}
_regions_map: dict = {}
_warning_type_map: dict = {}
_warning_group_map: dict = {}
_warning_severity_map: dict = {}


def get_weather_description_by_code(language: str, code: int | None) -> str:
    """
    Get the weather description by the weather code
    """
    global _weather_code_map
    if not _weather_code_map:
        with _cache_lock:
            if not _weather_code_map:
                _weather_code_map = _get_weather_codes(language)
    if not code:
        return "Nothing"
    code = int(code)
    return _weather_code_map.get(code, "Nothing")


def _get_weather_codes(language) -> dict:
    """
    Get the weather codes from IMS
    """
    try:
        url = WEATHER_CODES_URL.format(language=language)
        data = fetch_data(url)
        return {int(d["weather_code"]): d["desc"] for d in data["data"].values()}
    except Exception as e:
        logger.error("Error getting weather codes. " + str(e))
        return EN_WEATHER_CODES


def get_location_name_by_id(language: str, lid: str | int):
    """
    Converts location id to City name
    """
    lid = int(lid)
    global _locations_map
    if not _locations_map:
        with _cache_lock:
            if not _locations_map:
                _locations_map = _get_locations_map(language)
    location = _locations_map.get(lid)
    return location["name"] if location else "Nothing"


def get_location_info_by_id(language: str, lid: str | int):
    """
    Converts location id to City name
    """
    lid = int(lid)
    global _locations_map
    if not _locations_map:
        with _cache_lock:
            if not _locations_map:
                _locations_map = _get_locations_map(language)
    return _locations_map.get(int(lid))


def _get_locations_map(language) -> dict:
    """
    Get the location information from IMS
    """
    try:
        url = LOCATIONS_INFO_URL.format(language=language)
        data = fetch_data(url)
        return {int(d["lid"]): d for d in data["data"].values()}
    except Exception as e:
        logger.error("Error getting locations info.. " + str(e))
        return EN_LOCATIONS


def get_wind_direction(language: str, direction_code: int) -> int:
    """
    Converts the wind direction code to azimuth
    """
    global _wind_direction_map
    if not _wind_direction_map:
        with _cache_lock:
            if not _wind_direction_map:
                _wind_direction_map = _get_wind_direction_map(language)
    direction = _wind_direction_map.get(direction_code)
    if not direction:
        return -1
    if isinstance(direction, int):
        return direction
    return int(direction.get("direction"))


def _get_wind_direction_map(language) -> dict:
    """
    Get the Wind Direction Map from IMS
    """
    try:
        url = WIND_DIRECTIONS_URL.format(language=language)
        data = fetch_data(url)
        return {int(k): v for k, v in data["data"].items()}
    except Exception as e:
        logger.error("Error getting directions info.. " + str(e))
        return EN_WIND_DIRECTIONS


def _ensure_regions_map(language: str) -> None:
    """
    Populate the regions map if it is not loaded yet.
    """
    global _regions_map
    if not _regions_map:
        with _cache_lock:
            if not _regions_map:
                _regions_map = _get_regions(language)


def get_region_by_id(language: str, region_id: str) -> dict:
    """
    Get Region Information by Id
    """
    _ensure_regions_map(language)
    return _regions_map.get(region_id, {})


def warm_warning_caches(language: str) -> None:
    """
    Load the maps that Warning resolves its names against.

    Those lookups sit in Warning.__post_init__ and are lazy, so without this
    the first alert of a batch is the one that goes to the network -- a
    constructor doing I/O, with any failure surfacing from inside a
    dataclass. Calling this before the parse loop keeps the fetch in the
    open. Both halves already degrade to an empty map, so it cannot raise.
    """
    _load_warning_maps(language)
    _ensure_regions_map(language)


def _get_regions(language) -> dict:
    """
    Get the Regions Map from IMS

    An empty map on failure rather than an exception: the callers resolve
    names off it and can live without one. It is falsy, so the next call
    retries the fetch instead of caching the failure.
    """
    try:
        url = REGIONS_URL.format(language=language)
        data = fetch_data(url)
        return {v["rid"]: v for v in data["data"]}
    except Exception as e:
        logger.warning("Error getting Regions info: %s", e)
        return {}


def _get_warning_metadata(language) -> dict:
    """
    Get the Warning Types Map from IMS

    Empty on failure, for the same reason as _get_regions: a warning with an
    unresolved severity name is still worth showing, and the next call
    retries.
    """
    try:
        url = WARNINGS_METADTA_URL.format(language=language)
        data = fetch_data(url)
        return data["data"]
    except Exception as e:
        logger.warning("Error getting Warning Metadata: %s", e)
        return {}


def _load_warning_maps(language) -> None:
    """
    Populate the warning type, group and severity maps in one go.

    They all come from the same metadata document, so fetching it once and
    filling the three maps together keeps them consistent.
    """
    global _warning_type_map
    global _warning_group_map
    global _warning_severity_map

    if _warning_type_map:
        return

    with _cache_lock:
        if _warning_type_map:
            return

        metadata = _get_warning_metadata(language)
        if not metadata:
            return

        # .get rather than [...]: IMS dropping or renaming one of these
        # sections must not raise out of the Warning constructor that is
        # asking for a name.
        _warning_type_map = {
            int(v["warning_type_id"]): v
            for v in metadata.get("ims_warning_type", {}).values()
        }
        _warning_group_map = dict(metadata.get("warning_groups", {}))
        _warning_severity_map = {
            int(v["severity_id"]): v
            for v in metadata.get("warning_severity", {}).values()
        }


def get_warning_type_by_id(language: str, warning_type_id: int) -> dict:
    """
    Get the Warning Types by Id, or {} if it does not resolve.

    These three used to raise when the metadata had not loaded. They are
    called from Warning.__post_init__, so the exception came out of a
    constructor and took every warning in the batch with it. An empty dict
    leaves the name blank instead, and the alert text still gets through.
    """
    _load_warning_maps(language)
    return _warning_type_map.get(warning_type_id, {})


def get_warning_group_by_id(language: str, warning_group_id: str) -> dict:
    """
    Get the Warning Group by Id, or {} if it does not resolve.
    """
    _load_warning_maps(language)
    return _warning_group_map.get(warning_group_id, {})


def get_warning_severity_by_id(language: str, warning_severity_id: int) -> dict:
    """
    Get the Warning Severity by Id, or {} if it does not resolve.
    """
    _load_warning_maps(language)
    return _warning_severity_map.get(warning_severity_id, {})


def get_day_of_the_week(language: str, date: datetime):
    """
    Converts the given date to day of the week name
    """
    return date.strftime("%A")


def get_value(
    data: dict,
    key: str,
    inner_dict_key: str | None,
    data_type: type = dict,
    default_value=None,
    custom_empty_value=None,
):
    """
    Get default value from nested dictionary and convert to specified data type
    :param data: dictionary
    :param key: first level key
    :param inner_dict_key: second level key
    :param data_type: data type to convert to (str, int, float)
    :param default_value: default value
    :return: data[key][dict_key] or data[key] or default_value
    """
    value = None
    if data and key in data:
        entry = data.get(key)
        if inner_dict_key is None:
            value = entry
        elif isinstance(entry, dict):
            value = entry.get(inner_dict_key)

    if value is None:
        return default_value

    try:
        if data_type is str:
            value = str(value)
        if data_type is int:
            value = int(value)
        if data_type is float:
            value = float(value)
    except (ValueError, TypeError):
        value = default_value

    if custom_empty_value and value == custom_empty_value:
        return default_value
    return value


def fetch_data(url: str) -> dict:
    """
    Helper method to get the Json data from ims website
    """
    try:
        logger.debug("Getting data from: %s", url)
        response = _session.get(url, timeout=15)
        return json.loads(response.text)
    except Exception as e:
        # Every caller degrades on an empty dict, and the coordinator is what
        # reports a genuinely failed update, so this is a warning rather than
        # an error: IMS answering one endpoint with a stub is routine.
        logger.warning("Error getting data from %s: %s", url, e)
        return {}


def get_data(current_data, url, last_fetch_time, cache_expiration_in_sec) -> dict:
    """
    Return the cached document while it is fresh, otherwise fetch it again.

    ``last_fetch_time`` may be None on the first call; the short-circuit on
    ``current_data`` keeps the subtraction from running in that case.
    """
    if (
        current_data
        and last_fetch_time
        and (datetime.now() - last_fetch_time).total_seconds() < cache_expiration_in_sec
    ):
        return current_data
    try:
        logger.debug("Getting data from " + url)
        return fetch_data(url).get("data", {})
    except Exception as e:
        logger.error("Error getting city portal data. " + str(e))
    return {}
