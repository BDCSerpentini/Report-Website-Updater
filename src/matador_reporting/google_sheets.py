from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

from matador_reporting.core.errors import GoogleSheetsError
from matador_reporting.reports.email_template_performance.models import (
    EmailPerformanceResult,
)
from matador_reporting.reports.matador_dashboard import MatadorDashboardResult
from matador_reporting.reports.lead_source_performance import LeadSourcePerformanceResult
from matador_reporting.reports.volie_sms_service_appointments import (
    VolieSmsServiceAppointmentsResult,
)


SPREADSHEET_ID_PATTERN = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)")
METRIC_HEADERS = ("Sent", "Opens", "Open Rate", "CTA Users", "CTR", "CTOR")
MONTH_FILLS = ("#4459B8", "#596DE1", "#7283E8")
DASHBOARD_TITLE = "Matador Dashboard"
DASHBOARD_HEADERS = (
    "Leads",
    "Engaged Contacts",
    "Lead → Engaged",
    "Total Appointments",
    "Lead → Appointment Rate",
    "AI Influenced Appointments",
    "AI Appt %",
)
DASHBOARD_LOCATIONS = ("Medina", "CDJR", "Strongsville", "Tallmadge", "Westlake", "Willoughby", "Orrville")
LEAD_SOURCE_TITLE = "Lead Source Performance"
VOLIE_SERVICE_TITLE = "Volie SMS Service Appointments"
VOLIE_SERVICE_HEADERS = ("Bitly Clicks", "GA4 Active Users", "GA4 Users ÷ Clicks")
LEAD_SOURCE_HEADERS = (
    "Rank", "Lead Source", "Dealers", "Leads", "Engaged Leads", "Engagement Rate",
    "AI Influenced Appointments", "AI Influenced Appointment Rate", "User Appointments", "AI Appointments",
    "AI Appointment Rate", "Team Loop-Ins", "Loop-In Rate",
)
EMAIL_COMPARISON_START_COLUMN = 22
EMAIL_COMPARISON_METRICS = (
    ("OPEN RATE", 2),
    ("CTR", 4),
    ("CTOR", 5),
)


@dataclass(frozen=True)
class SheetWriteResult:
    spreadsheet_url: str
    worksheet_title: str
    updated_rows: int
    month_name: str


def spreadsheet_id(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise GoogleSheetsError("Enter the destination Google Spreadsheet URL or ID.")
    match = SPREADSHEET_ID_PATTERN.search(cleaned)
    if match:
        return match.group(1)
    if re.fullmatch(r"[a-zA-Z0-9-_]{20,}", cleaned):
        return cleaned
    raise GoogleSheetsError("The Google Spreadsheet URL or ID is not valid.")


def quarter_number(reporting_month: date) -> int:
    return ((reporting_month.month - 1) // 3) + 1


def worksheet_title(reporting_month: date) -> str:
    return "Email Template Performance"


def quarter_months(reporting_month: date) -> tuple[int, int, int]:
    first = (quarter_number(reporting_month) - 1) * 3 + 1
    return first, first + 1, first + 2


def column_letter(number: int) -> str:
    if number < 1:
        raise ValueError("Column numbers start at 1")
    letters = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def month_start_column(reporting_month: date) -> int:
    month_index = quarter_months(reporting_month).index(reporting_month.month)
    return 3 + (month_index * len(METRIC_HEADERS))


def service_account_client(credentials: Mapping[str, Any]):
    required = {"type", "project_id", "private_key", "client_email", "token_uri"}
    missing = sorted(required.difference(credentials))
    if missing:
        raise GoogleSheetsError(
            "[google_service_account] is missing: " + ", ".join(missing)
        )
    try:
        import gspread

        return gspread.service_account_from_dict(dict(credentials))
    except Exception as exc:
        raise GoogleSheetsError(
            "Google authentication failed. Check the service-account values in .streamlit/secrets.toml."
        ) from exc


def _worksheet(spreadsheet, title: str, rows: int = 120, cols: int = 20):
    try:
        return spreadsheet.worksheet(title), False
    except Exception as exc:
        if exc.__class__.__name__ != "WorksheetNotFound":
            raise
        return spreadsheet.add_worksheet(title=title, rows=rows, cols=cols), True


def _initialize_layout(worksheet, reporting_month: date) -> None:
    worksheet.resize(rows=120, cols=36)
    months = quarter_months(reporting_month)
    worksheet.update(
        range_name="A1:B2",
        values=[["Location", "Template / Campaign"], ["Location", "Template / Campaign"]],
    )
    worksheet.merge_cells("A1:A2")
    worksheet.merge_cells("B1:B2")

    for index, month in enumerate(months):
        start = 3 + index * len(METRIC_HEADERS)
        end = start + len(METRIC_HEADERS) - 1
        start_letter = column_letter(start)
        end_letter = column_letter(end)
        label = date(reporting_month.year, month, 1).strftime("%B").upper()
        worksheet.update(range_name=f"{start_letter}1", values=[[label]])
        worksheet.merge_cells(f"{start_letter}1:{end_letter}1")
        worksheet.update(
            range_name=f"{start_letter}2:{end_letter}2",
            values=[list(METRIC_HEADERS)],
        )

    worksheet.freeze(rows=2, cols=2)
    worksheet.format(
        "A1:T2",
        {
            "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
            "horizontalAlignment": "CENTER",
            "verticalAlignment": "MIDDLE",
        },
    )
    worksheet.format("A1:B2", {"backgroundColor": {"red": 0.09, "green": 0.14, "blue": 0.24}})
    for index, _month in enumerate(months):
        start = 3 + index * len(METRIC_HEADERS)
        end = start + len(METRIC_HEADERS) - 1
        fill = MONTH_FILLS[index]
        rgb = tuple(int(fill[position : position + 2], 16) / 255 for position in (1, 3, 5))
        worksheet.format(
            f"{column_letter(start)}1:{column_letter(end)}2",
            {"backgroundColor": {"red": rgb[0], "green": rgb[1], "blue": rgb[2]}},
        )
    worksheet.format(
        "A:T",
        {
            "textFormat": {"fontFamily": "Arial"},
            "verticalAlignment": "MIDDLE",
        },
    )
    worksheet.columns_auto_resize(0, 20)


def _email_comparison_rows(
    previous_start: int,
    current_start: int,
    metric_offset: int,
    last_row: int,
) -> list[list[Any]]:
    previous_column = column_letter(previous_start + metric_offset)
    current_column = column_letter(current_start + metric_offset)
    rows: list[list[Any]] = []
    for source_row in range(3, last_row + 1):
        previous = f"{previous_column}{source_row}"
        current = f"{current_column}{source_row}"
        rows.append(
            [
                f'=IF(A{source_row}="","",A{source_row})',
                f'=IF(B{source_row}="","",B{source_row})',
                f'=IF({previous}="","",{previous})',
                f'=IF({current}="","",{current})',
                f'=IF(OR({previous}="",{current}=""),"",{current}-{previous})',
            ]
        )
    return rows


def _write_email_comparison(worksheet, reporting_month: date, last_row: int) -> None:
    worksheet.batch_clear(["V1:AJ120"])
    month_index = quarter_months(reporting_month).index(reporting_month.month)
    if month_index == 0:
        worksheet.update(
            range_name="V1",
            values=[["MONTH-OVER-MONTH COMPARISON — Previous month unavailable in this quarter"]],
        )
        worksheet.format(
            "V1:AJ1",
            {
                "backgroundColor": {"red": 0.93, "green": 0.95, "blue": 1.0},
                "textFormat": {"bold": True},
            },
        )
        return

    previous_month = date(reporting_month.year, reporting_month.month - 1, 1)
    previous_start = 3 + (month_index - 1) * len(METRIC_HEADERS)
    current_start = 3 + month_index * len(METRIC_HEADERS)
    previous_label = previous_month.strftime("%B %Y").upper()
    current_label = reporting_month.strftime("%B %Y").upper()

    for section_index, (metric, metric_offset) in enumerate(EMAIL_COMPARISON_METRICS):
        start = EMAIL_COMPARISON_START_COLUMN + section_index * 5
        end = start + 4
        start_letter, end_letter = column_letter(start), column_letter(end)
        worksheet.update(
            range_name=f"{start_letter}1",
            values=[[f"{metric} — {previous_label} VS {current_label}"]],
        )
        worksheet.update(
            range_name=f"{start_letter}2:{end_letter}2",
            values=[["Location", "Template / Campaign", "Previous", "Current", "PP Change"]],
        )
        worksheet.batch_update(
            [
                {
                    "range": f"{start_letter}3:{end_letter}{last_row}",
                    "values": _email_comparison_rows(
                        previous_start,
                        current_start,
                        metric_offset,
                        last_row,
                    ),
                }
            ],
            value_input_option="USER_ENTERED",
        )
        worksheet.format(
            f"{start_letter}1:{end_letter}2",
            {
                "backgroundColor": {"red": 0.27, "green": 0.48, "blue": 0.70},
                "textFormat": {
                    "bold": True,
                    "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                },
                "horizontalAlignment": "CENTER",
            },
        )
        worksheet.format(
            f"{column_letter(start + 2)}3:{end_letter}{last_row}",
            {"numberFormat": {"type": "PERCENT", "pattern": "0.00%"}},
        )


def _existing_rows(worksheet) -> tuple[dict[tuple[str, str], int], int]:
    values = worksheet.get_all_values()
    rows: dict[tuple[str, str], int] = {}
    for row_number, row in enumerate(values[2:], start=3):
        location = row[0].strip() if len(row) > 0 else ""
        campaign = row[1].strip() if len(row) > 1 else ""
        if location and campaign:
            rows[(location.casefold(), campaign.casefold())] = row_number
    return rows, max(3, len(values) + 1)


def _month_values(row: int, start_column: int, sent: int, opened: int, cta_users: int) -> list[Any]:
    sent_cell = f"{column_letter(start_column)}{row}"
    opened_cell = f"{column_letter(start_column + 1)}{row}"
    cta_cell = f"{column_letter(start_column + 3)}{row}"
    return [
        sent,
        opened,
        f'=IFERROR({opened_cell}/{sent_cell},"")',
        cta_users,
        f'=IFERROR({cta_cell}/{sent_cell},"")',
        f'=IFERROR({cta_cell}/{opened_cell},"")',
    ]


def _apply_month_border(
    worksheet,
    first_row: int,
    last_row: int,
    start_column: int,
    end_column: int,
) -> None:
    border = {
        "style": "SOLID_MEDIUM",
        "color": {"red": 0, "green": 0, "blue": 0},
    }
    worksheet.spreadsheet.batch_update(
        {
            "requests": [
                {
                    "updateBorders": {
                        "range": {
                            "sheetId": worksheet.id,
                            "startRowIndex": first_row - 1,
                            "endRowIndex": last_row,
                            "startColumnIndex": start_column - 1,
                            "endColumnIndex": end_column,
                        },
                        "top": border,
                        "bottom": border,
                        "left": border,
                        "right": border,
                    }
                }
            ]
        }
    )


def write_email_performance(
    client,
    spreadsheet_url_or_id: str,
    reporting_month: date,
    location: str,
    result: EmailPerformanceResult,
) -> SheetWriteResult:
    if result.location_metrics is None:
        raise GoogleSheetsError("Generate the complete three-file report before exporting it.")
    key = spreadsheet_id(spreadsheet_url_or_id)
    title = worksheet_title(reporting_month)
    stage = "opening the spreadsheet"
    try:
        spreadsheet = client.open_by_key(key)
        stage = "preparing the quarterly tab"
        worksheet, created = _worksheet(spreadsheet, title, rows=120, cols=36)
        if created:
            _initialize_layout(worksheet, reporting_month)
        else:
            existing_values = worksheet.get_all_values()
            if not existing_values:
                _initialize_layout(worksheet, reporting_month)
            elif existing_values[0][:2] != ["Location", "Template / Campaign"]:
                raise GoogleSheetsError(
                    f"The existing {title} tab was not created by this reporting app. "
                    "Rename that tab or choose a different spreadsheet to prevent overwriting it."
                )

        worksheet.resize(
            rows=max(120, getattr(worksheet, "row_count", 120)),
            cols=36,
        )

        row_map, next_row = _existing_rows(worksheet)
        start_column = month_start_column(reporting_month)
        start_letter = column_letter(start_column)
        end_letter = column_letter(start_column + len(METRIC_HEADERS) - 1)
        updates: list[dict[str, Any]] = []
        updated_rows: list[int] = []

        report_rows = [
            (item.reporting_group, item.emails_sent, item.emails_opened, item.cta_users or 0)
            for item in result.campaigns
        ]
        totals = result.location_metrics
        report_rows.append(("Location Total", totals.emails_sent, totals.emails_opened, totals.unique_cta_users))

        for campaign, sent, opened, cta_users in report_rows:
            row_key = (location.casefold(), campaign.casefold())
            row = row_map.get(row_key)
            if row is None:
                row = next_row
                next_row += 1
                row_map[row_key] = row
                updates.append({"range": f"A{row}:B{row}", "values": [[location, campaign]]})
            updates.append(
                {
                    "range": f"{start_letter}{row}:{end_letter}{row}",
                    "values": [[*_month_values(row, start_column, sent, opened, cta_users)]],
                }
            )
            updated_rows.append(row)

        stage = "writing the report values"
        worksheet.batch_update(updates, value_input_option="USER_ENTERED")
        first_row, last_row = min(updated_rows), max(updated_rows)
        stage = "formatting the report"
        worksheet.format(f"C{first_row}:T{last_row}", {"horizontalAlignment": "RIGHT"})
        for index in (2, 4, 5):
            column = column_letter(start_column + index)
            worksheet.format(f"{column}{first_row}:{column}{last_row}", {"numberFormat": {"type": "PERCENT", "pattern": "0.00%"}})
        _apply_month_border(
            worksheet,
            first_row,
            last_row,
            start_column,
            start_column + len(METRIC_HEADERS) - 1,
        )
        total_row = row_map[(location.casefold(), "location total")]
        worksheet.format(
            f"A{total_row}:T{total_row}",
            {"backgroundColor": {"red": 0.93, "green": 0.95, "blue": 1.0}, "textFormat": {"bold": True}},
        )
        stage = "building the month-over-month comparison"
        _write_email_comparison(worksheet, reporting_month, max(row_map.values()))
        worksheet.columns_auto_resize(0, 20)
        return SheetWriteResult(
            spreadsheet_url=f"https://docs.google.com/spreadsheets/d/{key}",
            worksheet_title=title,
            updated_rows=len(report_rows),
            month_name=reporting_month.strftime("%B %Y"),
        )
    except GoogleSheetsError:
        raise
    except Exception as exc:
        detail = " ".join(str(exc).split())[:350]
        raise GoogleSheetsError(
            f"Google Sheets export failed while {stage}: {detail or exc.__class__.__name__}"
        ) from exc


def _initialize_dashboard_layout(worksheet, reporting_month: date) -> None:
    months = quarter_months(reporting_month)
    last_column = 1 + len(months) * len(DASHBOARD_HEADERS)
    worksheet.resize(rows=40, cols=last_column)
    worksheet.update(range_name="A1", values=[["Location"]])
    worksheet.merge_cells("A1:A2")
    worksheet.update(
        range_name=f"A3:A{3 + len(DASHBOARD_LOCATIONS)}",
        values=[[location] for location in DASHBOARD_LOCATIONS] + [["Total"]],
    )
    for index, month in enumerate(months):
        start = 2 + index * len(DASHBOARD_HEADERS)
        end = start + len(DASHBOARD_HEADERS) - 1
        start_letter = column_letter(start)
        end_letter = column_letter(end)
        label = date(reporting_month.year, month, 1).strftime("%B %Y").upper()
        worksheet.update(range_name=f"{start_letter}1", values=[[label]])
        worksheet.merge_cells(f"{start_letter}1:{end_letter}1")
        worksheet.update(range_name=f"{start_letter}2:{end_letter}2", values=[list(DASHBOARD_HEADERS)])
    worksheet.freeze(rows=2, cols=1)
    worksheet.format(
        f"A1:{column_letter(last_column)}2",
        {
            "backgroundColor": {"red": 0.27, "green": 0.48, "blue": 0.70},
            "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
            "horizontalAlignment": "CENTER",
            "verticalAlignment": "MIDDLE",
        },
    )
    worksheet.format(
        f"A3:{column_letter(last_column)}{3 + len(DASHBOARD_LOCATIONS)}",
        {"textFormat": {"fontFamily": "Arial"}, "verticalAlignment": "MIDDLE"},
    )
    worksheet.columns_auto_resize(0, last_column)


def _reset_dashboard_layout(worksheet, reporting_month: date) -> None:
    worksheet.spreadsheet.batch_update(
        {
            "requests": [
                {
                    "unmergeCells": {
                        "range": {
                            "sheetId": worksheet.id,
                            "startRowIndex": 0,
                            "endRowIndex": 2,
                            "startColumnIndex": 0,
                            "endColumnIndex": worksheet.col_count,
                        }
                    }
                }
            ]
        }
    )
    worksheet.clear()
    _initialize_dashboard_layout(worksheet, reporting_month)


def _dashboard_values(row: int, start_column: int, metrics) -> list[Any]:
    leads = f"{column_letter(start_column)}{row}"
    engaged = f"{column_letter(start_column + 1)}{row}"
    appointments = f"{column_letter(start_column + 3)}{row}"
    influenced = f"{column_letter(start_column + 5)}{row}"
    return [
        metrics.leads,
        metrics.engaged_contacts,
        f'=IFERROR({engaged}/{leads},"")',
        metrics.total_appointments,
        f'=IFERROR({appointments}/{leads},"")',
        metrics.ai_influenced_appointments,
        f'=IFERROR({influenced}/{appointments},"")',
    ]


def _dashboard_comparison_rows(
    reporting_month: date,
    previous_start: int,
    current_start: int,
    metric_offset: int,
    rate_metric: bool,
) -> list[list[Any]]:
    previous_column = column_letter(previous_start + metric_offset)
    current_column = column_letter(current_start + metric_offset)
    rows = []
    for source_row, location in enumerate((*DASHBOARD_LOCATIONS, "Total"), start=3):
        previous = f"{previous_column}{source_row}"
        current = f"{current_column}{source_row}"
        difference = f'=IF(OR({previous}="",{current}=""),"",{current}-{previous})'
        row = [
            location,
            f'=IF({previous}="","",{previous})',
            f'=IF({current}="","",{current})',
            difference,
        ]
        if not rate_metric:
            row.append(
                f'=IFERROR(IF(OR({previous}="",{current}=""),"",({current}-{previous})/{previous}),"")'
            )
        rows.append(row)
    return rows


def _write_dashboard_comparison(worksheet, reporting_month: date) -> None:
    blank = [[""] * 11 for _ in range(21)]
    worksheet.update(range_name="A12:K32", values=blank)
    month_index = quarter_months(reporting_month).index(reporting_month.month)
    if month_index == 0:
        worksheet.update(
            range_name="A12",
            values=[["MONTH-OVER-MONTH COMPARISON — Previous month unavailable in this quarter"]],
        )
        worksheet.format(
            "A12:K12",
            {
                "backgroundColor": {"red": 0.93, "green": 0.95, "blue": 1.0},
                "textFormat": {"bold": True},
            },
        )
        return

    previous_month = date(reporting_month.year, reporting_month.month - 1, 1)
    previous_start = 2 + (month_index - 1) * len(DASHBOARD_HEADERS)
    current_start = 2 + month_index * len(DASHBOARD_HEADERS)
    previous_label = previous_month.strftime("%B %Y").upper()
    current_label = reporting_month.strftime("%B %Y").upper()
    sections = (
        ("A", "E", 12, "LEADS", 0, False),
        ("G", "K", 12, "APPOINTMENTS", 3, False),
        ("A", "D", 23, "LEAD → APPOINTMENT RATE", 4, True),
        ("G", "J", 23, "AI APPT %", 6, True),
    )
    for start_letter, end_letter, title_row, title, offset, is_rate in sections:
        header_row = title_row + 1
        first_data_row = title_row + 2
        last_data_row = first_data_row + len(DASHBOARD_LOCATIONS)
        worksheet.update(
            range_name=f"{start_letter}{title_row}",
            values=[[f"{title} — {previous_label} VS {current_label}"]],
        )
        headers = (
            ["Location", "Previous", "Current", "PP Change"]
            if is_rate
            else ["Location", "Previous", "Current", "Difference", "% Change"]
        )
        worksheet.update(
            range_name=f"{start_letter}{header_row}:{end_letter}{header_row}",
            values=[headers],
        )
        worksheet.batch_update(
            [
                {
                    "range": f"{start_letter}{first_data_row}:{end_letter}{last_data_row}",
                    "values": _dashboard_comparison_rows(
                        reporting_month,
                        previous_start,
                        current_start,
                        offset,
                        is_rate,
                    ),
                }
            ],
            value_input_option="USER_ENTERED",
        )
        worksheet.format(
            f"{start_letter}{title_row}:{end_letter}{header_row}",
            {
                "backgroundColor": {"red": 0.27, "green": 0.48, "blue": 0.70},
                "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "horizontalAlignment": "CENTER",
            },
        )
        worksheet.format(
            f"{start_letter}{last_data_row}:{end_letter}{last_data_row}",
            {"backgroundColor": {"red": 0.58, "green": 0.75, "blue": 0.49}, "textFormat": {"bold": True}},
        )
        start_number_column = column_letter(_column_number_for_a1(start_letter) + 1)
        if is_rate:
            worksheet.format(
                f"{start_number_column}{first_data_row}:{end_letter}{last_data_row}",
                {"numberFormat": {"type": "PERCENT", "pattern": "0.00%"}},
            )
        else:
            percent_column = end_letter
            worksheet.format(
                f"{percent_column}{first_data_row}:{percent_column}{last_data_row}",
                {"numberFormat": {"type": "PERCENT", "pattern": "0.00%"}},
            )


def _column_number_for_a1(letters: str) -> int:
    number = 0
    for letter in letters:
        number = number * 26 + ord(letter) - 64
    return number


def write_matador_dashboard(
    client,
    spreadsheet_url_or_id: str,
    reporting_month: date,
    result: MatadorDashboardResult,
) -> SheetWriteResult:
    key = spreadsheet_id(spreadsheet_url_or_id)
    stage = "opening the spreadsheet"
    try:
        spreadsheet = client.open_by_key(key)
        stage = "preparing the Matador Dashboard tab"
        worksheet, created = _worksheet(
            spreadsheet,
            DASHBOARD_TITLE,
            rows=40,
            cols=1 + 3 * len(DASHBOARD_HEADERS),
        )
        if created:
            _initialize_dashboard_layout(worksheet, reporting_month)
        else:
            existing = worksheet.get_all_values()
            if not existing:
                _initialize_dashboard_layout(worksheet, reporting_month)
            elif existing[0][:1] != ["Location"]:
                raise GoogleSheetsError(
                    "The existing Matador Dashboard tab was not created by this reporting app. "
                    "Rename that tab or choose a different spreadsheet to prevent overwriting it."
                )
            else:
                first_quarter_month = quarter_months(reporting_month)[0]
                expected_first_header = date(
                    reporting_month.year, first_quarter_month, 1
                ).strftime("%B %Y").upper()
                current_first_header = existing[0][1] if len(existing[0]) > 1 else ""
                if current_first_header != expected_first_header:
                    _reset_dashboard_layout(worksheet, reporting_month)

        month_index = quarter_months(reporting_month).index(reporting_month.month)
        start_column = 2 + month_index * len(DASHBOARD_HEADERS)
        end_column = start_column + len(DASHBOARD_HEADERS) - 1
        start_letter = column_letter(start_column)
        end_letter = column_letter(end_column)
        row_by_location = {location: index + 3 for index, location in enumerate(DASHBOARD_LOCATIONS)}
        updates = []
        for metrics in result.locations:
            row = row_by_location[metrics.location]
            updates.append({"range": f"{start_letter}{row}:{end_letter}{row}", "values": [[*_dashboard_values(row, start_column, metrics)]]})
        total_row = 3 + len(DASHBOARD_LOCATIONS)
        updates.append({"range": f"{start_letter}{total_row}:{end_letter}{total_row}", "values": [[*_dashboard_values(total_row, start_column, result.totals)]]})

        stage = "writing the Matador Dashboard values"
        worksheet.batch_update(updates, value_input_option="USER_ENTERED")
        stage = "formatting the Matador Dashboard"
        for offset in (2, 4, 6):
            column = column_letter(start_column + offset)
            worksheet.format(f"{column}3:{column}{total_row}", {"numberFormat": {"type": "PERCENT", "pattern": "0.00%"}})
        worksheet.format(
            f"A{total_row}:{end_letter}{total_row}",
            {"backgroundColor": {"red": 0.58, "green": 0.75, "blue": 0.49}, "textFormat": {"bold": True}},
        )
        _apply_month_border(worksheet, 1, total_row, start_column, end_column)
        stage = "building the month-over-month comparison"
        _write_dashboard_comparison(worksheet, reporting_month)
        worksheet.columns_auto_resize(0, 1 + 3 * len(DASHBOARD_HEADERS))
        return SheetWriteResult(
            spreadsheet_url=f"https://docs.google.com/spreadsheets/d/{key}",
            worksheet_title=DASHBOARD_TITLE,
            updated_rows=len(result.locations) + 1,
            month_name=reporting_month.strftime("%B %Y"),
        )
    except GoogleSheetsError:
        raise
    except Exception as exc:
        detail = " ".join(str(exc).split())[:350]
        raise GoogleSheetsError(
            f"Google Sheets export failed while {stage}: {detail or exc.__class__.__name__}"
        ) from exc


def _initialize_lead_source_layout(worksheet, reporting_month: date) -> None:
    months = quarter_months(reporting_month)
    last_column = len(months) * len(LEAD_SOURCE_HEADERS)
    worksheet.resize(rows=24, cols=last_column)
    for index, month in enumerate(months):
        start = 1 + index * len(LEAD_SOURCE_HEADERS)
        end = start + len(LEAD_SOURCE_HEADERS) - 1
        start_letter, end_letter = column_letter(start), column_letter(end)
        label = date(reporting_month.year, month, 1).strftime("%B %Y").upper()
        worksheet.update(range_name=f"{start_letter}1", values=[[label]])
        worksheet.merge_cells(f"{start_letter}1:{end_letter}1")
        worksheet.update(range_name=f"{start_letter}2:{end_letter}2", values=[list(LEAD_SOURCE_HEADERS)])
    worksheet.freeze(rows=2)
    worksheet.format(
        f"A1:{column_letter(last_column)}2",
        {
            "backgroundColor": {"red": 0.27, "green": 0.48, "blue": 0.70},
            "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
            "horizontalAlignment": "CENTER",
            "verticalAlignment": "MIDDLE",
        },
    )
    worksheet.columns_auto_resize(0, last_column)


def _reset_lead_source_layout(worksheet, reporting_month: date) -> None:
    worksheet.spreadsheet.batch_update({"requests": [{"unmergeCells": {"range": {"sheetId": worksheet.id, "startRowIndex": 0, "endRowIndex": 2, "startColumnIndex": 0, "endColumnIndex": worksheet.col_count}}}]})
    worksheet.clear()
    _initialize_lead_source_layout(worksheet, reporting_month)


def _lead_source_values(row: int, start: int, item) -> list[Any]:
    leads = f"{column_letter(start + 3)}{row}"
    engaged = f"{column_letter(start + 4)}{row}"
    influenced_appts = f"{column_letter(start + 6)}{row}"
    ai_appts = f"{column_letter(start + 9)}{row}"
    loops = f"{column_letter(start + 11)}{row}"
    return [
        item.rank, item.lead_source, item.dealers, item.leads, item.engaged_leads,
        f'=IFERROR({engaged}/{leads},"")', item.ai_influenced_appointments,
        f'=IFERROR({influenced_appts}/{leads},"")', item.user_appointments, item.ai_appointments,
        f'=IFERROR({ai_appts}/{leads},"")', item.team_loop_ins,
        f'=IFERROR({loops}/{leads},"")',
    ]


def _lead_source_total_values(start: int, first_row: int = 3, last_row: int = 17) -> list[Any]:
    def total(offset: int) -> str:
        column = column_letter(start + offset)
        return f"=SUM({column}{first_row}:{column}{last_row})"

    leads = f"{column_letter(start + 3)}18"
    engaged = f"{column_letter(start + 4)}18"
    influenced_appts = f"{column_letter(start + 6)}18"
    ai_appts = f"{column_letter(start + 9)}18"
    loops = f"{column_letter(start + 11)}18"
    return [
        "",
        "Top 15 Total",
        "",
        total(3),
        total(4),
        f'=IFERROR({engaged}/{leads},"")',
        total(6),
        f'=IFERROR({influenced_appts}/{leads},"")',
        total(8),
        total(9),
        f'=IFERROR({ai_appts}/{leads},"")',
        total(11),
        f'=IFERROR({loops}/{leads},"")',
    ]


def write_lead_source_performance(client, spreadsheet_url_or_id: str, reporting_month: date, result: LeadSourcePerformanceResult) -> SheetWriteResult:
    key = spreadsheet_id(spreadsheet_url_or_id)
    stage = "opening the spreadsheet"
    try:
        spreadsheet = client.open_by_key(key)
        stage = "preparing the Lead Source Performance tab"
        worksheet, created = _worksheet(spreadsheet, LEAD_SOURCE_TITLE, rows=24, cols=3 * len(LEAD_SOURCE_HEADERS))
        if created:
            _initialize_lead_source_layout(worksheet, reporting_month)
        else:
            existing = worksheet.get_all_values()
            expected = date(reporting_month.year, quarter_months(reporting_month)[0], 1).strftime("%B %Y").upper()
            if not existing:
                _initialize_lead_source_layout(worksheet, reporting_month)
            elif len(existing) < 2 or not existing[1] or existing[1][0] != "Rank":
                raise GoogleSheetsError("The existing Lead Source Performance tab was not created by this reporting app. Rename it or choose a different spreadsheet.")
            elif not existing[0] or existing[0][0] != expected:
                _reset_lead_source_layout(worksheet, reporting_month)

        month_index = quarter_months(reporting_month).index(reporting_month.month)
        start = 1 + month_index * len(LEAD_SOURCE_HEADERS)
        end = start + len(LEAD_SOURCE_HEADERS) - 1
        updates = []
        for row, item in enumerate(result.top_sources, start=3):
            updates.append({"range": f"{column_letter(start)}{row}:{column_letter(end)}{row}", "values": [[*_lead_source_values(row, start, item)]]})
        updates.append(
            {
                "range": f"{column_letter(start)}18:{column_letter(end)}18",
                "values": [[*_lead_source_total_values(start)]],
            }
        )
        worksheet.batch_clear([f"{column_letter(start)}3:{column_letter(end)}18"])
        worksheet.batch_update(updates, value_input_option="USER_ENTERED")
        for offset in (5, 7, 10, 12):
            column = column_letter(start + offset)
            worksheet.format(f"{column}3:{column}18", {"numberFormat": {"type": "PERCENT", "pattern": "0.00%"}})
        worksheet.format(
            f"{column_letter(start)}18:{column_letter(end)}18",
            {"backgroundColor": {"red": 0.58, "green": 0.75, "blue": 0.49}, "textFormat": {"bold": True}},
        )
        _apply_month_border(worksheet, 1, 18, start, end)
        worksheet.columns_auto_resize(0, 3 * len(LEAD_SOURCE_HEADERS))
        return SheetWriteResult(f"https://docs.google.com/spreadsheets/d/{key}", LEAD_SOURCE_TITLE, len(result.top_sources) + 1, reporting_month.strftime("%B %Y"))
    except GoogleSheetsError:
        raise
    except Exception as exc:
        detail = " ".join(str(exc).split())[:350]
        raise GoogleSheetsError(f"Google Sheets export failed while {stage}: {detail or exc.__class__.__name__}") from exc


def _initialize_volie_service_layout(worksheet, reporting_month: date) -> None:
    months = quarter_months(reporting_month)
    last_row = 3 + len(DASHBOARD_LOCATIONS)
    last_column = 1 + len(months) * len(VOLIE_SERVICE_HEADERS)
    worksheet.resize(rows=last_row, cols=last_column)
    worksheet.update(range_name="A1", values=[["Location"]])
    worksheet.merge_cells("A1:A2")
    worksheet.update(
        range_name=f"A3:A{last_row}",
        values=[[location] for location in DASHBOARD_LOCATIONS] + [["Total"]],
    )
    for index, month in enumerate(months):
        start = 2 + index * len(VOLIE_SERVICE_HEADERS)
        end = start + len(VOLIE_SERVICE_HEADERS) - 1
        start_letter = column_letter(start)
        end_letter = column_letter(end)
        label = date(reporting_month.year, month, 1).strftime("%B %Y").upper()
        worksheet.update(range_name=f"{start_letter}1", values=[[label]])
        worksheet.merge_cells(f"{start_letter}1:{end_letter}1")
        worksheet.update(
            range_name=f"{start_letter}2:{end_letter}2",
            values=[list(VOLIE_SERVICE_HEADERS)],
        )
    worksheet.freeze(rows=2, cols=1)
    worksheet.format(
        f"A1:{column_letter(last_column)}2",
        {
            "backgroundColor": {"red": 0.27, "green": 0.48, "blue": 0.70},
            "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
            "horizontalAlignment": "CENTER",
            "verticalAlignment": "MIDDLE",
        },
    )
    worksheet.format(
        f"A{last_row}:{column_letter(last_column)}{last_row}",
        {"backgroundColor": {"red": 0.58, "green": 0.75, "blue": 0.49}, "textFormat": {"bold": True}},
    )
    worksheet.columns_auto_resize(0, last_column)


def _reset_volie_service_layout(worksheet, reporting_month: date) -> None:
    worksheet.spreadsheet.batch_update(
        {"requests": [{"unmergeCells": {"range": {
            "sheetId": worksheet.id,
            "startRowIndex": 0,
            "endRowIndex": 2,
            "startColumnIndex": 0,
            "endColumnIndex": worksheet.col_count,
        }}}]}
    )
    worksheet.clear()
    _initialize_volie_service_layout(worksheet, reporting_month)


def write_volie_sms_service_appointments(
    client,
    spreadsheet_url_or_id: str,
    reporting_month: date,
    result: VolieSmsServiceAppointmentsResult,
) -> SheetWriteResult:
    key = spreadsheet_id(spreadsheet_url_or_id)
    stage = "opening the spreadsheet"
    try:
        spreadsheet = client.open_by_key(key)
        stage = "preparing the Volie SMS Service Appointments tab"
        worksheet, created = _worksheet(
            spreadsheet,
            VOLIE_SERVICE_TITLE,
            rows=12,
            cols=1 + 3 * len(VOLIE_SERVICE_HEADERS),
        )
        if created:
            _initialize_volie_service_layout(worksheet, reporting_month)
        else:
            existing = worksheet.get_all_values()
            expected = date(reporting_month.year, quarter_months(reporting_month)[0], 1).strftime("%B %Y").upper()
            if not existing:
                _initialize_volie_service_layout(worksheet, reporting_month)
            elif (
                len(existing) < 2
                or not existing[0]
                or existing[0][0] != "Location"
                or len(existing[1]) < 2
                or existing[1][1] != "Bitly Clicks"
            ):
                if len(existing) >= 2 and existing[0] and existing[0][0] == "Location":
                    _reset_volie_service_layout(worksheet, reporting_month)
                    existing = worksheet.get_all_values()
                else:
                    raise GoogleSheetsError(
                        "The existing Volie SMS Service Appointments tab was not created by this reporting app. "
                        "Rename it or choose a different spreadsheet."
                    )
            elif len(existing[0]) < 2 or existing[0][1] != expected:
                _reset_volie_service_layout(worksheet, reporting_month)

        month_index = quarter_months(reporting_month).index(reporting_month.month)
        start_column = 2 + month_index * len(VOLIE_SERVICE_HEADERS)
        end_column = start_column + len(VOLIE_SERVICE_HEADERS) - 1
        start_letter = column_letter(start_column)
        active_letter = column_letter(start_column + 1)
        end_letter = column_letter(end_column)
        row_by_location = {
            location: index + 3 for index, location in enumerate(DASHBOARD_LOCATIONS)
        }
        updates = []
        for item in result.locations:
            row = row_by_location[item.location]
            clicks = item.bitly_clicks if item.bitly_clicks is not None else ""
            active_users = item.active_users if item.active_users is not None else ""
            rate = (
                f'=IFERROR({active_letter}{row}/{start_letter}{row},"")'
                if item.bitly_clicks is not None and item.active_users is not None
                else ""
            )
            updates.append(
                {
                    "range": f"{start_letter}{row}:{end_letter}{row}",
                    "values": [[clicks, active_users, rate]],
                }
            )
        total_row = 3 + len(DASHBOARD_LOCATIONS)
        total_clicks = result.comparable_bitly_clicks if result.total_bitly_clicks else ""
        total_active = (
            result.comparable_active_users if result.total_bitly_clicks else result.total_active_users
        )
        total_rate = (
            f'=IFERROR({active_letter}{total_row}/{start_letter}{total_row},"")'
            if result.total_bitly_clicks else ""
        )
        updates.append(
            {
                "range": f"{start_letter}{total_row}:{end_letter}{total_row}",
                "values": [[total_clicks, total_active, total_rate]],
            }
        )
        updates.append(
            {
                "range": f"A{total_row}",
                "values": [["Comparable Total" if result.total_bitly_clicks else "Total"]],
            }
        )
        stage = "writing the service-appointment values"
        worksheet.batch_update(updates, value_input_option="USER_ENTERED")
        rate_column = column_letter(start_column + 2)
        worksheet.format(
            f"{rate_column}3:{rate_column}{total_row}",
            {"numberFormat": {"type": "PERCENT", "pattern": "0.00%"}},
        )
        _apply_month_border(worksheet, 1, total_row, start_column, end_column)
        worksheet.columns_auto_resize(0, 1 + 3 * len(VOLIE_SERVICE_HEADERS))
        return SheetWriteResult(
            f"https://docs.google.com/spreadsheets/d/{key}",
            VOLIE_SERVICE_TITLE,
            len(result.locations) + 1,
            reporting_month.strftime("%B %Y"),
        )
    except GoogleSheetsError:
        raise
    except Exception as exc:
        detail = " ".join(str(exc).split())[:350]
        raise GoogleSheetsError(
            f"Google Sheets export failed while {stage}: {detail or exc.__class__.__name__}"
        ) from exc
