"""Smoke tests for the vendored weatheril library.

These do not assert exact weather values, which change with every capture.
They check that each response still parses into the expected shape and that
the fields the integration reads are populated.
"""

import copy
import datetime
import logging


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


def test_empty_current_analysis_degrades_quietly(weather, monkeypatch, caplog):
    """IMS sometimes answers an endpoint with an empty or non-JSON body.

    Returning None is the right outcome — the coordinator turns it into a
    failed update and retries. It has to get there without an exception: the
    empty payload used to reach a log line that concatenated a dict onto a
    string, and the resulting TypeError was swallowed by the except branch,
    which is why a plain "returns None" assertion would not catch it.
    """
    from ims_motinium import weatheril as weatheril_pkg

    monkeypatch.setattr(weatheril_pkg, "fetch_data", lambda url: {})
    caplog.set_level(logging.DEBUG)

    assert weather.get_current_analysis() is None
    logged = [record for record in caplog.records if record.exc_info]
    assert not logged, f"an exception was logged while degrading: {logged}"


def _land_alerts(payload):
    """The alerts filed against r-97, the region of the fixture's location."""
    return payload["data"]["full_warnings_data"]["2026-07-25"]["r-97"]


def test_warnings_survive_unreadable_metadata(weather, serve):
    """A warning with no severity name still beats no warning at all.

    The severity, type and group lookups sit in Warning.__post_init__ and
    used to raise when the metadata had not loaded, which came out of the
    constructor and cost every alert in the batch. The coordinator reports
    that as "no active warnings" -- the one answer a warnings feed must not
    give wrongly.
    """
    serve("warnings_metadata", {})

    warnings = weather.get_warnings()

    assert warnings, "the alert should survive its metadata being unreadable"
    assert warnings[0].text_full, "and still carry the text the user acts on"
    assert warnings[0].severity == ""
    assert warnings[0].warning_type == ""


def test_warnings_survive_unreadable_regions(weather, serve):
    """Same for the regions map, which had no fallback of its own."""
    serve("regions", {})

    warnings = weather.get_warnings()

    assert warnings
    assert warnings[0].region_name == ""
    assert warnings[0].regions == []


def test_an_unknown_group_id_does_not_lose_the_warning(
    weather, serve, warnings_payload
):
    """IMS adding a group id used to KeyError out of the constructor."""
    alert = next(iter(_land_alerts(warnings_payload).values()))
    alert["groups"] = [*alert["groups"], "999999"]
    serve("warnings", warnings_payload)

    warnings = weather.get_warnings()

    assert warnings
    assert warnings[0].groups, "the groups that do resolve are still named"
    assert all(group for group in warnings[0].groups), "no blank group names"


def test_one_unparsable_alert_does_not_drop_the_others(
    weather, serve, warnings_payload, caplog
):
    """A single bad alert is skipped, not the whole batch."""
    alerts = _land_alerts(warnings_payload)
    good = next(iter(alerts.values()))
    broken = copy.deepcopy(good)
    broken["wid"] = "999999"
    broken["valid_from"] = "whenever"
    alerts["999999"] = broken
    serve("warnings", warnings_payload)

    warnings = weather.get_warnings()

    assert [w.wid for w in warnings] == [int(good["wid"])]
    assert any("did not parse" in record.message for record in caplog.records)


def test_the_same_alert_on_several_days_is_returned_once(
    weather, serve, warnings_payload
):
    """One alert spanning two dates used to produce two identical warnings."""
    days = warnings_payload["data"]["full_warnings_data"]
    days["2026-07-26"]["r-97"] = copy.deepcopy(days["2026-07-25"]["r-97"])
    serve("warnings", warnings_payload)

    wids = [w.wid for w in weather.get_warnings()]

    assert wids
    assert len(wids) == len(set(wids))


def test_warnings_for_an_unknown_location_are_empty(weather):
    """An unresolvable location returns nothing instead of raising."""
    weather.location = "999999"

    assert weather.get_warnings() == []


def test_radar_lists_are_per_instance(weather):
    """Mutable default arguments used to share one list between instances."""
    from ims_motinium.weatheril.radar_satellite import RadarSatellite

    first, second = RadarSatellite(), RadarSatellite()
    first.imsradar_images.append("x")

    assert second.imsradar_images == []
