from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from matador_reporting.core.errors import InvalidReportError


EVENT_NAMES = {
    "form_submission_service_appt",
    "asc_form_submission_service_appt",
}
PERIOD_PATTERN = re.compile(r"^#\s*(\d{8})-(\d{8})\s*$")
SERVICE_LOCATIONS = (
    "Medina", "CDJR", "Strongsville", "Tallmadge", "Westlake", "Willoughby", "Orrville",
)
LOCATION_ALIASES = {
    "Medina": ("medina",),
    "CDJR": ("cdjr", "cdrj", "north olmsted"),
    "Strongsville": ("strongsville",),
    "Tallmadge": ("tallmadge",),
    "Westlake": ("westlake",),
    "Willoughby": ("willoughby",),
    "Orrville": ("orrville",),
}


@dataclass(frozen=True)
class ServiceAppointmentLocation:
    location: str
    active_users: int | None
    event_name: str | None
    bitly_clicks: int | None = None
    ga4_report_uploaded: bool = True

    @property
    def event_found(self) -> bool:
        return self.ga4_report_uploaded and self.event_name is not None

    @property
    def appointment_rate(self) -> float | None:
        if self.active_users is None or not self.bitly_clicks:
            return None
        return self.active_users / self.bitly_clicks


@dataclass(frozen=True)
class VolieSmsServiceAppointmentsResult:
    period_start: date
    period_end: date
    locations: tuple[ServiceAppointmentLocation, ...]

    @property
    def total_active_users(self) -> int:
        return sum(item.active_users or 0 for item in self.locations)

    @property
    def total_bitly_clicks(self) -> int:
        return sum(item.bitly_clicks or 0 for item in self.locations)

    @property
    def comparable_bitly_clicks(self) -> int:
        return sum(
            item.bitly_clicks or 0
            for item in self.locations
            if item.active_users is not None and item.bitly_clicks is not None
        )

    @property
    def comparable_active_users(self) -> int:
        return sum(
            item.active_users or 0
            for item in self.locations
            if item.active_users is not None and item.bitly_clicks is not None
        )

    @property
    def overall_appointment_rate(self) -> float | None:
        if not self.comparable_bitly_clicks:
            return None
        return self.comparable_active_users / self.comparable_bitly_clicks


class VolieSmsServiceAppointmentsProcessor:
    @staticmethod
    def _integer(value: str, filename: str, column: str = "Active users") -> int:
        try:
            return int(value.replace(",", "").strip())
        except (AttributeError, ValueError) as exc:
            raise InvalidReportError(
                f"{filename} contains an invalid {column} value: {value!r}"
            ) from exc

    @staticmethod
    def _period(lines: list[str], filename: str) -> tuple[date, date]:
        for line in lines:
            match = PERIOD_PATTERN.match(line.strip())
            if not match:
                continue
            try:
                return tuple(
                    datetime.strptime(value, "%Y%m%d").date()
                    for value in match.groups()
                )  # type: ignore[return-value]
            except ValueError as exc:
                raise InvalidReportError(
                    f"{filename} contains an invalid reporting period"
                ) from exc
        raise InvalidReportError(
            f"{filename} does not contain the GA4 reporting-period header"
        )

    def _process_file(self, location: str, path: Path) -> tuple[date, date, ServiceAppointmentLocation]:
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except (OSError, UnicodeError) as exc:
            raise InvalidReportError(f"Could not read GA4 CSV: {path.name}") from exc

        period_start, period_end = self._period(lines, path.name)
        data_lines = [line for line in lines if line.strip() and not line.lstrip().startswith("#")]
        try:
            reader = csv.DictReader(data_lines)
            fields = tuple(reader.fieldnames or ())
            missing = [column for column in ("Event name", "Active users") if column not in fields]
            if missing:
                raise InvalidReportError(f"{path.name} is missing: {', '.join(missing)}")
            matches = [
                row for row in reader
                if (row.get("Event name") or "").strip().casefold() in EVENT_NAMES
            ]
        except InvalidReportError:
            raise
        except csv.Error as exc:
            raise InvalidReportError(f"Could not parse GA4 CSV: {path.name}") from exc

        if len(matches) > 1:
            raise InvalidReportError(
                f"{path.name} contains multiple service-appointment event rows"
            )
        if not matches:
            return period_start, period_end, ServiceAppointmentLocation(location, 0, None)
        event_name = (matches[0].get("Event name") or "").strip()
        active_users = self._integer(matches[0].get("Active users") or "", path.name)
        return period_start, period_end, ServiceAppointmentLocation(location, active_users, event_name)

    @staticmethod
    def _bitly_location(row: dict[str, str]) -> str | None:
        label = (row.get("Link") or "").strip().casefold()
        destination = (row.get("Destination URL") or "").strip().casefold()
        is_service = (
            "schedule service" in label
            or "scheduler" in label
            or "utm_campaign=service_reschedule" in destination
        )
        if not is_service:
            return None
        for location, aliases in LOCATION_ALIASES.items():
            if any(alias in label for alias in aliases):
                return location
        return None

    def _process_bitly(self, path: Path) -> dict[str, int]:
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                fields = tuple(reader.fieldnames or ())
                missing = [column for column in ("Link", "Clicks", "Destination URL") if column not in fields]
                if missing:
                    raise InvalidReportError(f"{path.name} is missing: {', '.join(missing)}")
                clicks: dict[str, int] = {}
                for row in reader:
                    location = self._bitly_location(row)
                    if location is None:
                        continue
                    clicks[location] = clicks.get(location, 0) + self._integer(
                        row.get("Clicks") or "", path.name, "Clicks"
                    )
        except InvalidReportError:
            raise
        except (OSError, UnicodeError, csv.Error) as exc:
            raise InvalidReportError(f"Could not read Bitly CSV: {path.name}") from exc
        if not clicks:
            raise InvalidReportError(
                "The Bitly report does not contain any recognized Schedule Service links"
            )
        return clicks

    def process(
        self,
        uploads: dict[str, Path],
        bitly_path: Path | None = None,
    ) -> VolieSmsServiceAppointmentsResult:
        if not uploads:
            raise InvalidReportError("Upload at least one location's GA4 service report")

        expected_period: tuple[date, date] | None = None
        ga4_locations: dict[str, ServiceAppointmentLocation] = {}
        for location, path in uploads.items():
            period_start, period_end, metrics = self._process_file(location, path)
            period = (period_start, period_end)
            if expected_period is None:
                expected_period = period
            elif period != expected_period:
                raise InvalidReportError(
                    "The uploaded GA4 service reports contain conflicting reporting periods"
                )
            ga4_locations[location] = metrics

        assert expected_period is not None
        bitly_clicks: dict[str, int] = {}
        if bitly_path is not None:
            bitly_clicks = self._process_bitly(bitly_path)

        locations = []
        for location in SERVICE_LOCATIONS:
            ga4 = ga4_locations.get(location)
            clicks = bitly_clicks.get(location)
            if ga4 is None and clicks is None:
                continue
            locations.append(
                ServiceAppointmentLocation(
                    location=location,
                    active_users=ga4.active_users if ga4 else None,
                    event_name=ga4.event_name if ga4 else None,
                    bitly_clicks=clicks,
                    ga4_report_uploaded=ga4 is not None,
                )
            )
        return VolieSmsServiceAppointmentsResult(*expected_period, tuple(locations))
