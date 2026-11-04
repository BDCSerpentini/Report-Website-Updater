from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from matador_reporting.core.errors import InvalidReportError
from matador_reporting.reports.email_template_performance.models import SourceMetadata


REQUIRED_COLUMNS = {"eMail Template", "Emails Sent", "Emails Opened"}
PERIOD_PATTERN = re.compile(
    r"Report Period:\s*(\d{1,2}/\d{1,2}/\d{4})\s*-\s*(\d{1,2}/\d{1,2}/\d{4})"
)


def normalize_template_name(value: str) -> str:
    """Normalize eLeads template labels without changing their real names."""
    name = str(value).strip()
    if name.startswith("="):
        name = name[1:].lstrip()
    return name


def _read_rows(path: Path) -> list[list[str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.reader(handle))
    except (OSError, UnicodeError, csv.Error) as exc:
        raise InvalidReportError(f"Could not read CSV: {path.name}") from exc


def parse_matador_email_performance(path: Path) -> tuple[SourceMetadata, pd.DataFrame]:
    rows = _read_rows(path)
    if not rows or not rows[0] or "Template Performance Report" not in rows[0][0]:
        raise InvalidReportError("File is not an Email Template Performance Report")

    header_index = next(
        (index for index, row in enumerate(rows) if row and row[0] == "eMail Template"),
        None,
    )
    if header_index is None:
        raise InvalidReportError("Could not locate the email template column header row")

    columns = rows[header_index]
    missing = REQUIRED_COLUMNS.difference(columns)
    if missing:
        raise InvalidReportError(
            "Email template report is missing required columns: " + ", ".join(sorted(missing))
        )

    metadata_text = " ".join(cell for row in rows[:header_index] for cell in row if cell)
    period_match = PERIOD_PATTERN.search(metadata_text)
    if not period_match:
        raise InvalidReportError("Could not determine the email template reporting period")

    dealership = rows[1][0].strip() if len(rows) > 1 and rows[1] else ""
    generated = rows[2][0].strip() if len(rows) > 2 and rows[2] else ""
    metadata = SourceMetadata(
        dealership=dealership,
        generated_text=generated.removeprefix("Generated:").strip(),
        period_start=datetime.strptime(period_match.group(1), "%m/%d/%Y").date(),
        period_end=datetime.strptime(period_match.group(2), "%m/%d/%Y").date(),
    )

    width = len(columns)
    data_rows = [row[:width] + [""] * max(0, width - len(row)) for row in rows[header_index + 1 :]]
    frame = pd.DataFrame(data_rows, columns=columns)
    frame = frame[frame["eMail Template"].notna()].copy()
    frame["eMail Template"] = frame["eMail Template"].map(normalize_template_name)
    frame = frame[(frame["eMail Template"] != "") & (frame["eMail Template"] != "Totals")]

    for column in ("Emails Sent", "Emails Opened"):
        converted = pd.to_numeric(frame[column], errors="coerce")
        if converted.isna().any():
            bad_templates = frame.loc[converted.isna(), "eMail Template"].tolist()
            raise InvalidReportError(
                f"{column} contains invalid counts for: {', '.join(bad_templates)}"
            )
        frame[column] = converted.astype(int)

    return metadata, frame[["eMail Template", "Emails Sent", "Emails Opened"]]
