from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from json import JSONEncoder

from .utils import (
    get_day_of_the_week,
    get_location_name_by_id,
    get_weather_description_by_code,
    get_wind_direction,
)


@dataclass
class Forecast:
    days: list[Daily] = field(default_factory=list)


@dataclass
class Daily:
    language: str
    date: datetime
    lid: str
    weather_code: int | None
    minimum_temperature: int
    maximum_temperature: int
    maximum_uvi: int
    u_v_i_factor: float
    description: str
    hours: list[Hourly] = field(default_factory=list)
    day: str = field(init=False)
    location: str = field(init=False)
    weather: str = field(init=False)

    def __post_init__(self):
        self.day = get_day_of_the_week(self.language, self.date)
        self.location = get_location_name_by_id(self.language, self.lid)
        self.weather = get_weather_description_by_code(self.language, self.weather_code)


@dataclass
class Hourly:
    language: str
    hour: str
    forecast_time: datetime
    created: datetime
    temperature: int | None
    precise_temperature: float | None
    weather_code: int | None
    heat_stress: float | None
    heat_stress_level: int | None
    pm10: int | None
    relative_humidity: int | None
    rain: float | None
    rain_chance: float | None
    wind_speed: int | None
    wind_direction_id: int | None
    wind_chill: int | None
    weather: str = field(init=False)
    wind_direction: str = field(init=False)
    wave_height: float | None
    u_v_index: int | None
    u_v_i_max: int | None
    gust_speed: int | None

    def __post_init__(self):
        self.weather = get_weather_description_by_code(self.language, self.weather_code)
        self.wind_direction = get_wind_direction(self.language, self.wind_direction_id)


class ForecastEncoder(JSONEncoder):
    """
    Return Contact object as json
    """

    def default(self, o):
        return o.__dict__
