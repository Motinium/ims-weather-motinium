from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RadarSatellite:
    """
    Image URLs published by the IMS radar/satellite endpoint.

    Only the lists IMS actually fills are kept. ``radar`` comes back empty and
    there is no ``EUROPE`` key in the response, so those two were dropped.

    Note that the IMS radar frames themselves are currently unusable: the
    per-frame PNG URLs answer 200 with a 2-byte placeholder body instead of an
    image. The satellite JPEGs are fine.
    """

    imsradar_images: list = field(default_factory=list)
    middle_east_satellite_images: list = field(default_factory=list)
