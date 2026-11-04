from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from matador_reporting.core.errors import InvalidReportError


@dataclass(frozen=True)
class LeadSourceMetrics:
    rank: int
    lead_source: str
    dealers: int
    leads: int
    engaged_leads: int
    ai_influenced_appointments: int
    user_appointments: int
    ai_appointments: int
    team_loop_ins: int

    @property
    def engagement_rate(self): return self.engaged_leads / self.leads if self.leads else None
    @property
    def ai_influenced_appointment_rate(self): return self.ai_influenced_appointments / self.leads if self.leads else None
    @property
    def ai_appointment_rate(self): return self.ai_appointments / self.leads if self.leads else None
    @property
    def loop_in_rate(self): return self.team_loop_ins / self.leads if self.leads else None


@dataclass(frozen=True)
class LeadSourcePerformanceResult:
    period_start: date
    period_end: date
    top_sources: tuple[LeadSourceMetrics, ...]
    all_source_count: int
    all_leads: int


class LeadSourcePerformanceProcessor:
    REQUIRED = (
        "Start Date", "End Date", "Lead Source", "Dealers", "Leads", "Engaged Leads",
        "AI Influenced Appointments", "User Appointments", "AI Appointments", "AI Looped Your Team In",
    )

    @staticmethod
    def _integer(value: str, column: str, filename: str) -> int:
        try:
            return int(value.replace(",", "").strip())
        except (AttributeError, ValueError) as exc:
            raise InvalidReportError(f"{filename} contains an invalid {column} value: {value!r}") from exc

    def _read(self, path: Path) -> tuple[date, date, list[dict[str, str | int]]]:
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                fields = tuple(reader.fieldnames or ())
                missing = [column for column in self.REQUIRED if column not in fields]
                if missing:
                    raise InvalidReportError(f"{path.name} is missing: {', '.join(missing)}")
                rows = list(reader)
        except InvalidReportError:
            raise
        except (OSError, UnicodeError, csv.Error) as exc:
            raise InvalidReportError(f"Could not read Lead Sources CSV: {path.name}") from exc
        if not rows:
            raise InvalidReportError("Lead Sources report contains no rows")
        periods = {(row["Start Date"], row["End Date"]) for row in rows}
        if len(periods) != 1:
            raise InvalidReportError("Lead Sources report contains conflicting reporting periods")
        start_text, end_text = periods.pop()
        try:
            period_start, period_end = date.fromisoformat(start_text), date.fromisoformat(end_text)
        except ValueError as exc:
            raise InvalidReportError("Lead Sources report contains an invalid reporting period") from exc

        parsed = []
        for row in rows:
            source = row["Lead Source"].strip()
            if not source:
                continue
            parsed.append(
                {
                    "lead_source": source,
                    **{column: self._integer(row[column], column, path.name) for column in self.REQUIRED[3:]},
                }
            )
        return period_start, period_end, parsed

    @staticmethod
    def _build_result(
        period_start: date,
        period_end: date,
        parsed: list[dict[str, str | int]],
    ) -> LeadSourcePerformanceResult:
        parsed.sort(key=lambda item: (-int(item["Leads"]), str(item["lead_source"]).casefold()))
        top = tuple(
            LeadSourceMetrics(
                rank=index,
                lead_source=str(item["lead_source"]),
                dealers=int(item["Dealers"]),
                leads=int(item["Leads"]),
                engaged_leads=int(item["Engaged Leads"]),
                ai_influenced_appointments=int(item["AI Influenced Appointments"]),
                user_appointments=int(item["User Appointments"]),
                ai_appointments=int(item["AI Appointments"]),
                team_loop_ins=int(item["AI Looped Your Team In"]),
            )
            for index, item in enumerate(parsed[:15], start=1)
        )
        return LeadSourcePerformanceResult(
            period_start, period_end, top, len(parsed),
            sum(int(item["Leads"]) for item in parsed),
        )

    def process(self, path: Path) -> LeadSourcePerformanceResult:
        period_start, period_end, parsed = self._read(path)
        return self._build_result(period_start, period_end, parsed)

    def process_many(self, paths: tuple[Path, ...] | list[Path]) -> LeadSourcePerformanceResult:
        if not paths:
            raise InvalidReportError("Upload at least one individual location report")

        combined: dict[str, dict[str, str | int]] = {}
        expected_period: tuple[date, date] | None = None
        numeric_columns = self.REQUIRED[3:]
        for path in paths:
            period_start, period_end, parsed = self._read(path)
            period = (period_start, period_end)
            if expected_period is None:
                expected_period = period
            elif period != expected_period:
                raise InvalidReportError(
                    "Individual location reports contain conflicting reporting periods"
                )
            for item in parsed:
                key = str(item["lead_source"]).casefold()
                if key not in combined:
                    combined[key] = {"lead_source": str(item["lead_source"])}
                    combined[key].update({column: 0 for column in numeric_columns})
                for column in numeric_columns:
                    combined[key][column] = int(combined[key][column]) + int(item[column])

        assert expected_period is not None
        return self._build_result(*expected_period, list(combined.values()))
