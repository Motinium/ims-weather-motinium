from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .consts import TIMEZONE
from .utils import (
    get_location_info_by_id,
    get_region_by_id,
    get_warning_group_by_id,
    get_warning_severity_by_id,
    get_warning_type_by_id,
)


@dataclass
class Warning:
    language: str
    location_id: int
    wid: int
    alert_id: int
    severity_id: int
    warning_type_id: int
    sent: str | datetime
    valid_from: str | datetime
    valid_to: str | datetime
    full_en: str
    full_he: str
    text: str
    text_full: str
    valid_from_unix: int
    groups: list[int | str]
    regions: list[int | str]
    region_name: str = field(init=False)
    severity: str = field(init=False)
    warning_type: str = field(init=False)

    def __post_init__(self):
        # Every name below is looked up, and a lookup that does not resolve
        # leaves the field blank rather than raising. The alert text is what
        # the user acts on; losing the whole warning because IMS could not
        # name its region would be the worse outcome.
        location_info = get_location_info_by_id(self.language, self.location_id)
        rid = location_info.get("rid") if location_info else None
        region = (
            get_region_by_id(self.language, region_id="r-" + str(rid)) if rid else {}
        )
        self.region_name = region.get("name", "")

        self.severity = get_warning_severity_by_id(self.language, self.severity_id).get(
            "severity_name", ""
        )
        self.warning_type = get_warning_type_by_id(
            self.language, int(self.warning_type_id)
        ).get("name", "")
        self.sent = (
            TIMEZONE.localize(datetime.strptime(self.sent, "%Y-%m-%d %H:%M:%S"))
            if isinstance(self.sent, str)
            else self.sent
        )
        self.valid_from = (
            TIMEZONE.localize(datetime.strptime(self.valid_from, "%Y-%m-%d %H:%M:%S"))
            if isinstance(self.valid_from, str)
            else self.valid_from
        )
        self.valid_to = (
            TIMEZONE.localize(datetime.strptime(self.valid_to, "%Y-%m-%d %H:%M:%S"))
            if isinstance(self.valid_to, str)
            else self.valid_to
        )

        # Names only: an id that does not resolve is dropped instead of
        # becoming an empty string, which would render as a blank chip on a
        # card. "g-..."["name"] used to KeyError on an id IMS had just added.
        self.groups = [
            name
            for gid in self.groups
            if (
                name := get_warning_group_by_id(self.language, "g-" + str(gid)).get(
                    "name"
                )
            )
        ]

        self.regions = [
            name
            for rid in self.regions
            if (name := get_region_by_id(self.language, "r-" + str(rid)).get("name"))
        ]

        if not self.text_full:
            self.text_full = (
                self.full_en.strip() if self.language == "en" else self.full_he.strip()
            )
