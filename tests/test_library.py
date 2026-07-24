"""Smoke tests for the vendored weatheril library.

These do not assert exact weather values, which change with every capture.
They check that each response still parses into the expected shape and that
the fields the integration reads are populated.
"""

import datetime


def test_current_analysis_parses(weather):
    current = weather.get_current_analysis()

    assert current is not None
    assert isinstance(current.temperature, float)
    assert 0 <= current.humidity <= 100
    assert current.location, "location name should resolve via locations_info"
    assert isinstance(current.forecast_time, datetime.datetime)
    # Timezone-aware: the sensors declare device_class timestamp.
    assert current.forecast_time.tzinfo is not None


def test_current_analysis_exposes_model_run_time(weather):
    """modified_at backs the ims_last_modified sensor."""
    current = weather.get_current_analysis()

    assert current.modified_at is not None
    assert current.modified_at.tzinfo is not None


def test_forecast_has_days_and_hours(weather):
    forecast = weather.get_forecast()

    assert forecast is not None
    assert len(forecast.days) >= 5
    assert all(day.date.tzinfo is not None for day in forecast.days)
    assert sum(len(day.hours) for day in forecast.days) > 50


def test_hourly_fields_used_by_the_digest_are_present(weather):
    """The digest rules read these off the Hourly objects."""
    forecast = weather.get_forecast()
    hours = [hour for day in forecast.days for hour in day.hours]

    assert hours
    for field in (
        "temperature",
        "relative_humidity",
        "wind_speed",
        "gust_speed",
        "u_v_index",
        "heat_stress_level",
    ):
        values = [getattr(hour, field) for hour in hours]
        assert any(value is not None for value in values), f"{field} is never set"


def test_hourly_forecast_survives_a_day_without_hours(weather):
    """A day with no hourly section must not blow up the whole forecast."""
    assert weather._get_hourly_forecast(None) == []
    assert weather._get_hourly_forecast({}) == []


def test_warnings_parse_with_resolved_metadata(weather):
    warnings = weather.get_warnings()

    for warning in warnings:
        assert warning.severity, "severity_id should resolve to a name"
        assert warning.warning_type, "warning_type_id should resolve to a name"
        assert warning.valid_from.tzinfo is not None
        assert warning.valid_to.tzinfo is not None
        # groups and regions are converted from ids to names in __post_init__
        assert all(isinstance(group, str) for group in warning.groups)
        assert all(isinstance(region, str) for region in warning.regions)


def test_sea_warnings_come_from_the_sea_regions(weather):
    """Marine alerts are filed against sea regions, not the location's own."""
    sea = weather.get_sea_warnings()
    land = weather.get_warnings()

    assert sea, "the captured fixture has active sea warnings"
    # The land region is r-97 (Akko / Zevulun Valley), which is not a sea one,
    # so the two sets are built from different regions.
    assert {w.wid for w in sea} != {w.wid for w in land}


def test_warnings_for_regions_deduplicates(weather):
    """One alert covering several regions is returned once."""
    combined = weather.get_warnings_for_regions(["r-54", "r-55", "r-56"])
    wids = [w.wid for w in combined]

    assert wids
    assert len(wids) == len(set(wids))


def test_warnings_for_unknown_region_is_empty(weather):
    assert weather.get_warnings_for_regions(["r-does-not-exist"]) == []


def test_cache_does_not_slide_on_a_hit(weather, monkeypatch):
    """The cache window must not move forward when data came from the cache.

    Refreshing the timestamp on every call kept the data from ever expiring
    for a caller polling faster than the expiry.
    """
    weather.get_current_analysis()
    first_fetch = weather._analysis_last_fetch
    assert first_fetch is not None

    weather.get_current_analysis()

    assert weather._analysis_last_fetch == first_fetch


def test_radar_lists_are_per_instance(weather):
    """Mutable default arguments used to share one list between instances."""
    from ims_motinium.weatheril.radar_satellite import RadarSatellite

    first, second = RadarSatellite(), RadarSatellite()
    first.imsradar_images.append("x")

    assert second.imsradar_images == []
