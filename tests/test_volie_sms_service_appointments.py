from datetime import date
import re

import pytest

from matador_reporting.core.errors import InvalidReportError
from matador_reporting.google_sheets import write_volie_sms_service_appointments
from matador_reporting.reports.volie_sms_service_appointments import (
    VolieSmsServiceAppointmentsProcessor,
)


HEADER = "Event name,Active users,Event count"


def _report(tmp_path, name, end_date, event_name, active_users):
    path = tmp_path / name
    rows = [
        "# Chevrolet - Test",
        "# Service Reports-SMS Event Tracking",
        f"# 20260801-{end_date}",
        "",
        HEADER,
        ",70,500,Grand total",
    ]
    if event_name is not None:
        rows.append(f"{event_name},{active_users},99")
    path.write_text("\n".join(rows), encoding="utf-8")
    return path


def _bitly_report(tmp_path):
    path = tmp_path / "bitly.csv"
    path.write_text(
        "\n".join([
            "Type,Link,Clicks,%,Short URL,Destination URL,Date Created",
            "Bitlink,Medina Schedule Service,40,1,https://bit.ly/serpentiniMD,https://example.com/?utm_campaign=service_reschedule,2026-01-01",
            "Bitlink,Willoughby Hills Schedule Service,68,1,https://bit.ly/serpentiniWH,https://example.com/?utm_campaign=service_reschedule,2026-01-01",
            "Bitlink,CDRJ Scheduler,52,1,https://bit.ly/serpentiniCDJR,https://example.com/?utm_campaign=service_reschedule,2026-01-01",
            "Bitlink,Medina Directions,99,1,https://bit.ly/directions,https://example.com/,2026-01-01",
        ]),
        encoding="utf-8",
    )
    return path


def test_parser_accepts_both_service_appointment_event_names(tmp_path):
    result = VolieSmsServiceAppointmentsProcessor().process(
        {
            "Medina": _report(tmp_path, "md.csv", "20260821", "asc_form_submission_service_appt", 26),
            "Willoughby": _report(tmp_path, "wh.csv", "20260821", "form_submission_service_appt", 40),
        }
    )
    assert result.period_start == date(2026, 8, 1)
    assert result.period_end == date(2026, 8, 21)
    assert result.total_active_users == 66
    assert result.locations[0].event_found


def test_missing_event_is_reported_as_zero(tmp_path):
    result = VolieSmsServiceAppointmentsProcessor().process(
        {"CDJR": _report(tmp_path, "cdjr.csv", "20260821", None, 0)}
    )
    assert result.locations[0].active_users == 0
    assert not result.locations[0].event_found


def test_conflicting_periods_are_rejected(tmp_path):
    with pytest.raises(InvalidReportError, match="conflicting reporting periods"):
        VolieSmsServiceAppointmentsProcessor().process(
            {
                "Medina": _report(tmp_path, "md.csv", "20260820", "asc_form_submission_service_appt", 26),
                "Westlake": _report(tmp_path, "wl.csv", "20260821", "asc_form_submission_service_appt", 31),
            }
        )


def test_bitly_schedule_service_clicks_are_compared_without_missing_ga4(tmp_path):
    result = VolieSmsServiceAppointmentsProcessor().process(
        {
            "Medina": _report(tmp_path, "md.csv", "20260821", "asc_form_submission_service_appt", 26),
            "Willoughby": _report(tmp_path, "wh.csv", "20260821", "form_submission_service_appt", 40),
        },
        _bitly_report(tmp_path),
    )
    assert result.total_bitly_clicks == 160
    assert result.comparable_bitly_clicks == 108
    assert result.comparable_active_users == 66
    assert result.overall_appointment_rate == pytest.approx(66 / 108)
    cdjr = next(item for item in result.locations if item.location == "CDJR")
    assert cdjr.bitly_clicks == 52
    assert cdjr.active_users is None
    assert cdjr.appointment_rate is None


def _column_number(letters):
    number = 0
    for letter in letters:
        number = number * 26 + ord(letter) - 64
    return number


class WorksheetNotFound(Exception):
    pass


class FakeWorksheet:
    def __init__(self, title, spreadsheet):
        self.title = title
        self.id = 1
        self.spreadsheet = spreadsheet
        self.grid = {}
        self.col_count = 4

    def _write(self, range_name, values):
        match = re.fullmatch(r"([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?", range_name)
        start_column = _column_number(match.group(1))
        start_row = int(match.group(2))
        for row_offset, row in enumerate(values):
            for column_offset, value in enumerate(row):
                self.grid[(start_row + row_offset, start_column + column_offset)] = value

    def update(self, range_name=None, values=None): self._write(range_name, values)
    def batch_update(self, updates, value_input_option=None):
        for update in updates: self._write(update["range"], update["values"])
    def get_all_values(self):
        if not self.grid: return []
        last_row = max(row for row, _ in self.grid)
        last_column = max(column for _, column in self.grid)
        return [[self.grid.get((row, column), "") for column in range(1, last_column + 1)] for row in range(1, last_row + 1)]
    def merge_cells(self, _range): pass
    def freeze(self, **_kwargs): pass
    def format(self, *_args, **_kwargs): pass
    def columns_auto_resize(self, *_args): pass
    def resize(self, **kwargs): self.col_count = kwargs.get("cols", self.col_count)
    def clear(self): self.grid.clear()


class FakeSpreadsheet:
    def __init__(self):
        self.worksheets = {}
        self.batch_calls = []
    def worksheet(self, title):
        if title not in self.worksheets: raise WorksheetNotFound(title)
        return self.worksheets[title]
    def add_worksheet(self, title, rows, cols):
        worksheet = FakeWorksheet(title, self)
        self.worksheets[title] = worksheet
        return worksheet
    def batch_update(self, body): self.batch_calls.append(body)


class FakeClient:
    def __init__(self): self.spreadsheet = FakeSpreadsheet()
    def open_by_key(self, _key): return self.spreadsheet


def test_google_sheets_writes_location_values_and_total_formula(tmp_path):
    result = VolieSmsServiceAppointmentsProcessor().process(
        {
            "Medina": _report(tmp_path, "md.csv", "20260821", "asc_form_submission_service_appt", 26),
            "Willoughby": _report(tmp_path, "wh.csv", "20260821", "form_submission_service_appt", 40),
        },
        _bitly_report(tmp_path),
    )
    client = FakeClient()
    write = write_volie_sms_service_appointments(
        client, "abcdefghijklmnopqrstuvwxyz123", date(2026, 8, 1), result
    )
    worksheet = client.spreadsheet.worksheets["Volie SMS Service Appointments"]
    assert write.updated_rows == 4
    assert worksheet.grid[(1, 2)] == "JULY 2026"
    assert worksheet.grid[(1, 5)] == "AUGUST 2026"
    assert worksheet.grid[(3, 5)] == 40
    assert worksheet.grid[(3, 6)] == 26
    assert worksheet.grid[(3, 7)] == '=IFERROR(F3/E3,"")'
    assert worksheet.grid[(8, 5)] == 68
    assert worksheet.grid[(8, 6)] == 40
    assert worksheet.grid[(10, 1)] == "Comparable Total"
    assert worksheet.grid[(10, 5)] == 108
    assert worksheet.grid[(10, 6)] == 66
    assert worksheet.grid[(10, 7)] == '=IFERROR(F10/E10,"")'
