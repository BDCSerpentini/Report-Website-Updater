from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path

from matador_reporting.core.errors import InvalidReportError
from matador_reporting.reports.email_template_performance.models import (
    GA4CampaignData,
    GA4Metadata,
    GA4Summary,
)


DATE_PATTERN = re.compile(r"^(\d{8})-(\d{8})$")


def _read_rows(path: Path) -> list[list[str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.reader(handle))
    except (OSError, UnicodeError, csv.Error) as exc:
        raise InvalidReportError(f"Could not read GA4 CSV: {path.name}") from exc


def _parse_metadata(rows: list[list[str]]) -> tuple[GA4Metadata, int]:
    comments = [row[0].removeprefix("#").strip() for row in rows if row and row[0].startswith("#")]
    date_text = next((value for value in comments if DATE_PATTERN.match(value)), None)
    if date_text is None:
        raise InvalidReportError("Could not determine the GA4 reporting period")
    match = DATE_PATTERN.match(date_text)
    assert match is not None

    meaningful = [value for value in comments if value and set(value) != {"-"} and value != date_text]
    if len(meaningful) < 2:
        raise InvalidReportError("GA4 metadata is missing the property or report name")

    header_index = next(
        (index for index, row in enumerate(rows) if row and not row[0].startswith("#") and any(row)),
        None,
    )
    if header_index is None:
        raise InvalidReportError("GA4 export does not contain a header row")

    return (
        GA4Metadata(
            property_name=meaningful[0],
            report_name=meaningful[1],
            period_start=datetime.strptime(match.group(1), "%Y%m%d").date(),
            period_end=datetime.strptime(match.group(2), "%Y%m%d").date(),
        ),
        header_index,
    )


def _integer(value: str, label: str) -> int:
    try:
        number = float(value)
    except ValueError as exc:
        raise InvalidReportError(f"GA4 {label} is not numeric: {value!r}") from exc
    if not number.is_integer() or number < 0:
        raise InvalidReportError(f"GA4 {label} must be a non-negative whole number")
    return int(number)


def parse_ga4_summary(path: Path) -> GA4Summary:
    rows = _read_rows(path)
    metadata, header_index = _parse_metadata(rows)
    header = rows[header_index]
    required = ("Total users", "Active users", "Sessions")
    missing = [column for column in required if column not in header]
    if missing:
        raise InvalidReportError("GA4 summary is missing: " + ", ".join(missing))
    records = [row for row in rows[header_index + 1 :] if row and any(cell.strip() for cell in row)]
    if not records:
        raise InvalidReportError("GA4 summary contains no totals")

    total_index = header.index("Total users")
    active_index = header.index("Active users")
    sessions_index = header.index("Sessions")
    grand_total_rows = [
        row
        for row in records
        if any(cell.strip().casefold() == "grand total" for cell in row)
    ]
    if len(grand_total_rows) > 1:
        raise InvalidReportError("GA4 summary contains more than one Grand total row")
    rows_to_parse = grand_total_rows or records
    parsed = {
        (
            _integer(row[total_index], "Total users"),
            _integer(row[active_index], "Active users"),
            _integer(row[sessions_index], "Sessions"),
        )
        for row in rows_to_parse
    }
    if len(parsed) != 1:
        raise InvalidReportError("GA4 summary contains conflicting total rows")
    total_users, active_users, sessions = parsed.pop()
    return GA4Summary(metadata, total_users, active_users, sessions)


def parse_ga4_campaign_matrix(path: Path) -> GA4CampaignData:
    rows = _read_rows(path)
    metadata, header_index = _parse_metadata(rows)
    cta_header = rows[header_index]
    if not cta_header or cta_header[0] != "Session manual ad content" or "Totals" not in cta_header:
        raise InvalidReportError("GA4 campaign matrix has an unexpected CTA header")
    if header_index + 1 >= len(rows):
        raise InvalidReportError("GA4 campaign matrix is missing its campaign header")
    metric_header = rows[header_index + 1]
    if not metric_header or metric_header[0] != "Session campaign":
        raise InvalidReportError("GA4 campaign matrix is missing Session campaign")

    candidate_metrics = ("Total users", "Active users")
    user_metric = next(
        (
            metric
            for metric in candidate_metrics
            if any(
                cta_header[index] == "Totals" and metric_header[index] == metric
                for index in range(1, min(len(cta_header), len(metric_header)))
            )
        ),
        None,
    )
    if user_metric is None:
        raise InvalidReportError(
            "GA4 campaign matrix must include Totals for Total users or Active users"
        )
    matching_total_columns = [
        index
        for index in range(1, min(len(cta_header), len(metric_header)))
        if cta_header[index] == "Totals" and metric_header[index] == user_metric
    ]
    if len(matching_total_columns) != 1:
        raise InvalidReportError(
            f"GA4 campaign matrix has an ambiguous Totals → {user_metric} column"
        )
    total_column = matching_total_columns[0]
    total_row = next(
        (row for row in rows[header_index + 2 :] if row and not row[0].strip()),
        None,
    )
    if total_row is None:
        raise InvalidReportError("GA4 campaign matrix is missing its grand total row")
    total_unique_users = _integer(total_row[total_column], "campaign-matrix total users")

    users_by_cta: dict[str, int] = {}
    for index in range(1, min(len(cta_header), len(metric_header))):
        cta_name = cta_header[index].strip()
        if cta_name == "Totals" or metric_header[index] != user_metric:
            continue
        if cta_name in users_by_cta:
            raise InvalidReportError(
                f"GA4 campaign matrix has more than one {cta_name} → {user_metric} column"
            )
        users_by_cta[cta_name] = _integer(
            total_row[index], f"{cta_name} {user_metric}"
        )
    users_by_campaign: dict[str, int] = {}
    for row in rows[header_index + 2 :]:
        campaign = row[0].strip() if row else ""
        if not campaign:
            continue
        if campaign in users_by_campaign:
            raise InvalidReportError(f"GA4 campaign appears more than once: {campaign}")
        users_by_campaign[campaign] = _integer(row[total_column], f"{campaign} Total users")

    return GA4CampaignData(
        metadata,
        total_unique_users,
        users_by_campaign,
        users_by_cta,
        user_metric,
    )
