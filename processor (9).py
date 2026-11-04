from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Mapping

from matador_reporting.core.errors import InvalidReportError
from matador_reporting.reports.email_template_performance.config import EMAIL_CONFIGS


@dataclass(frozen=True)
class DashboardLocationMetrics:
    location: str
    leads: int
    engaged_contacts: int
    total_appointments: int
    ai_influenced_appointments: int

    @property
    def lead_to_engaged(self) -> float | None:
        return self.engaged_contacts / self.leads if self.leads else None

    @property
    def lead_to_appointment(self) -> float | None:
        return self.total_appointments / self.leads if self.leads else None

    @property
    def ai_appointment_percent(self) -> float | None:
        return self.ai_influenced_appointments / self.total_appointments if self.total_appointments else None


@dataclass(frozen=True)
class MatadorDashboardSource:
    period_start: date
    period_end: date
    leads: Mapping[str, int]
    engaged_contacts: Mapping[str, int]
    ai_influenced_appointments: Mapping[str, int]

    @property
    def locations(self) -> tuple[str, ...]:
        return tuple(location for location in EMAIL_CONFIGS if location in self.leads)


@dataclass(frozen=True)
class MatadorDashboardResult:
    period_start: date
    period_end: date
    locations: tuple[DashboardLocationMetrics, ...]

    @property
    def totals(self) -> DashboardLocationMetrics:
        return DashboardLocationMetrics(
            location="Total",
            leads=sum(item.leads for item in self.locations),
            engaged_contacts=sum(item.engaged_contacts for item in self.locations),
            total_appointments=sum(item.total_appointments for item in self.locations),
            ai_influenced_appointments=sum(item.ai_influenced_appointments for item in self.locations),
        )


def _integer(value: str, column: str, filename: str) -> int:
    try:
        return int(str(value).replace(",", "").strip())
    except (TypeError, ValueError) as exc:
        raise InvalidReportError(f"{filename} contains an invalid {column} value: {value!r}") from exc


def _location(dealer: str) -> str:
    matches = [name for name, config in EMAIL_CONFIGS.items() if config.matches_location(dealer)]
    if len(matches) != 1:
        raise InvalidReportError(f"Could not match dealer to one configured location: {dealer or 'blank dealer'}")
    return matches[0]


INFLUENCED_COLUMN_ALIASES = ("Appts Influenced", "AI Influenced Appts")


def _read(path: Path, required: tuple[str, ...]) -> tuple[date, date, list[dict[str, str]]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = tuple(reader.fieldnames or ())
            missing = [
                column for column in required
                if column not in fields
                and not (
                    column == "Appts Influenced"
                    and any(alias in fields for alias in INFLUENCED_COLUMN_ALIASES)
                )
            ]
            if missing:
                raise InvalidReportError(f"{path.name} is missing: {', '.join(missing)}")
            rows = list(reader)
    except InvalidReportError:
        raise
    except (OSError, UnicodeError, csv.Error) as exc:
        raise InvalidReportError(f"Could not read Matador dashboard CSV: {path.name}") from exc
    if not rows:
        raise InvalidReportError(f"{path.name} contains no dealer rows")
    influenced_column = next(
        (alias for alias in INFLUENCED_COLUMN_ALIASES if alias in fields),
        None,
    )
    if "Appts Influenced" in required and influenced_column is not None:
        for row in rows:
            row["Appts Influenced"] = row[influenced_column]
    periods = {(row["Start Date"], row["End Date"]) for row in rows}
    if len(periods) != 1:
        raise InvalidReportError(f"{path.name} contains conflicting reporting periods")
    start_text, end_text = periods.pop()
    try:
        return date.fromisoformat(start_text), date.fromisoformat(end_text), rows
    except ValueError as exc:
        raise InvalidReportError(f"{path.name} contains an invalid reporting period") from exc


class MatadorDashboardProcessor:
    def process_sources(
        self,
        engage_path: Path,
        follow_up_path: Path,
        reply_path: Path,
    ) -> MatadorDashboardSource:
        specifications = (
            (engage_path, ("Start Date", "End Date", "Dealer", "Customers Messaged", "Customers Engaged", "Appts Influenced")),
            (follow_up_path, ("Start Date", "End Date", "Dealer", "Appts Influenced")),
            (reply_path, ("Start Date", "End Date", "Dealer", "Appts Influenced")),
        )
        parsed = [_read(path, required) for path, required in specifications]
        periods = {(start, end) for start, end, _rows in parsed}
        if len(periods) != 1:
            raise InvalidReportError("The three Matador Dashboard exports use different reporting periods")
        period_start, period_end = periods.pop()

        leads: dict[str, int] = {}
        engaged: dict[str, int] = {}
        influenced: dict[str, int] = {}
        for file_index, (path, _required) in enumerate(specifications):
            seen: set[str] = set()
            for row in parsed[file_index][2]:
                location = _location(row["Dealer"])
                if location in seen:
                    raise InvalidReportError(f"{path.name} contains more than one row for {location}")
                seen.add(location)
                influenced[location] = influenced.get(location, 0) + _integer(
                    row["Appts Influenced"], "Appts Influenced", path.name
                )
                if file_index == 0:
                    leads[location] = _integer(row["Customers Messaged"], "Customers Messaged", path.name)
                    engaged[location] = _integer(row["Customers Engaged"], "Customers Engaged", path.name)

        return MatadorDashboardSource(period_start, period_end, leads, engaged, influenced)

    def build_result(
        self,
        source: MatadorDashboardSource,
        total_appointments: Mapping[str, int],
    ) -> MatadorDashboardResult:
        rows = tuple(
            DashboardLocationMetrics(
                location=location,
                leads=source.leads[location],
                engaged_contacts=source.engaged_contacts[location],
                total_appointments=max(0, int(total_appointments.get(location, 0))),
                ai_influenced_appointments=source.ai_influenced_appointments.get(location, 0),
            )
            for location in source.locations
        )
        return MatadorDashboardResult(source.period_start, source.period_end, rows)
