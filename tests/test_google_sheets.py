from datetime import date
from pathlib import Path
import re

from matador_reporting.google_sheets import (
    month_start_column,
    quarter_number,
    spreadsheet_id,
    write_email_performance,
    worksheet_title,
)
from matador_reporting.reports.email_template_performance import (
    EmailTemplatePerformanceProcessor,
)


FIXTURES = Path(__file__).parent / "fixtures"


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
        self.id = len(spreadsheet.worksheets) + 1
        self.spreadsheet = spreadsheet
        self.grid = {}
        self.batch_calls = []
        self.format_calls = []
        self.row_count = 120
        self.col_count = 20

    def _write(self, range_name, values):
        match = re.fullmatch(r"([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?", range_name)
        assert match, range_name
        start_column = _column_number(match.group(1))
        start_row = int(match.group(2))
        for row_offset, row in enumerate(values):
            for column_offset, value in enumerate(row):
                self.grid[(start_row + row_offset, start_column + column_offset)] = value

    def update(self, range_name=None, values=None):
        self._write(range_name, values)

    def batch_update(self, updates, value_input_option=None):
        self.batch_calls.append(updates)
        for update in updates:
            self._write(update["range"], update["values"])

    def batch_clear(self, ranges):
        for range_name in ranges:
            match = re.fullmatch(r"([A-Z]+)(\d+):([A-Z]+)(\d+)", range_name)
            assert match, range_name
            first_column = _column_number(match.group(1))
            first_row = int(match.group(2))
            last_column = _column_number(match.group(3))
            last_row = int(match.group(4))
            for key in list(self.grid):
                row, column = key
                if first_row <= row <= last_row and first_column <= column <= last_column:
                    del self.grid[key]

    def get_all_values(self):
        if not self.grid:
            return []
        last_row = max(row for row, _column in self.grid)
        last_column = max(column for _row, column in self.grid)
        return [
            [self.grid.get((row, column), "") for column in range(1, last_column + 1)]
            for row in range(1, last_row + 1)
        ]

    def merge_cells(self, _range): pass
    def freeze(self, **_kwargs): pass
    def format(self, range_name, cell_format):
        self.format_calls.append((range_name, cell_format))
    def set_basic_filter(self, _range): pass
    def columns_auto_resize(self, *_args): pass
    def resize(self, rows=None, cols=None):
        if rows is not None:
            self.row_count = rows
        if cols is not None:
            self.col_count = cols


class FakeSpreadsheet:
    def __init__(self):
        self.worksheets = {}
        self.batch_calls = []

    def batch_update(self, body):
        self.batch_calls.append(body)

    def worksheet(self, title):
        if title not in self.worksheets:
            raise WorksheetNotFound(title)
        return self.worksheets[title]

    def add_worksheet(self, title, rows, cols):
        worksheet = FakeWorksheet(title, self)
        self.worksheets[title] = worksheet
        return worksheet


class FakeClient:
    def __init__(self):
        self.spreadsheet = FakeSpreadsheet()

    def open_by_key(self, _key):
        return self.spreadsheet


def _result():
    return EmailTemplatePerformanceProcessor().process(
        FIXTURES / "medina_email_performance.csv",
        FIXTURES / "ga4_summary.csv",
        FIXTURES / "ga4_campaign_matrix.csv",
    )


def test_quarter_helpers():
    august = date(2026, 8, 1)
    assert quarter_number(august) == 3
    assert worksheet_title(august) == "Email Template Performance"
    assert month_start_column(date(2026, 7, 1)) == 3
    assert month_start_column(august) == 9
    assert month_start_column(date(2026, 9, 1)) == 15
    assert spreadsheet_id("https://docs.google.com/spreadsheets/d/abcdefghijklmnopqrstuvwxyz123/edit") == "abcdefghijklmnopqrstuvwxyz123"


def test_export_updates_existing_rows_instead_of_duplicating():
    client = FakeClient()
    result = _result()
    target = "abcdefghijklmnopqrstuvwxyz123"

    first = write_email_performance(client, target, date(2026, 8, 1), "Medina", result)
    worksheet = client.spreadsheet.worksheets["Email Template Performance"]
    rows_after_first = len(worksheet.get_all_values())
    assert first.updated_rows == 16
    assert worksheet.grid[(3, 9)] == 377
    assert worksheet.grid[(3, 10)] == 110
    assert worksheet.grid[(3, 12)] == 10
    assert worksheet.grid[(18, 12)] == 31
    assert worksheet.grid[(1, 22)] == "OPEN RATE — JULY 2026 VS AUGUST 2026"
    assert worksheet.grid[(3, 24)] == '=IF(E3="","",E3)'
    assert worksheet.grid[(3, 25)] == '=IF(K3="","",K3)'
    assert worksheet.grid[(3, 26)] == '=IF(OR(E3="",K3=""),"",K3-E3)'
    assert worksheet.grid[(1, 27)] == "CTR — JULY 2026 VS AUGUST 2026"
    assert worksheet.grid[(1, 32)] == "CTOR — JULY 2026 VS AUGUST 2026"
    whole_sheet_format = next(
        cell_format
        for range_name, cell_format in worksheet.format_calls
        if range_name == "A:T"
    )
    assert whole_sheet_format["textFormat"]["fontFamily"] == "Arial"
    assert "fontFamily" not in whole_sheet_format
    border_request = client.spreadsheet.batch_calls[0]["requests"][0]["updateBorders"]
    assert border_request["range"] == {
        "sheetId": worksheet.id,
        "startRowIndex": 2,
        "endRowIndex": 18,
        "startColumnIndex": 8,
        "endColumnIndex": 14,
    }
    assert border_request["top"]["style"] == "SOLID_MEDIUM"
    assert border_request["top"]["color"] == {"red": 0, "green": 0, "blue": 0}

    write_email_performance(client, target, date(2026, 8, 1), "Medina", result)
    assert len(worksheet.get_all_values()) == rows_after_first

    write_email_performance(client, target, date(2026, 7, 1), "Medina", result)
    assert len(worksheet.get_all_values()) == rows_after_first
    assert worksheet.grid[(3, 3)] == 377
    assert worksheet.grid[(3, 9)] == 377


def test_locations_get_separate_rows():
    client = FakeClient()
    result = _result()
    target = "abcdefghijklmnopqrstuvwxyz123"
    month = date(2026, 8, 1)

    write_email_performance(client, target, month, "Medina", result)
    write_email_performance(client, target, month, "Strongsville", result)
    worksheet = client.spreadsheet.worksheets["Email Template Performance"]

    assert worksheet.grid[(3, 1)] == "Medina"
    assert worksheet.grid[(19, 1)] == "Strongsville"
    assert worksheet.grid[(19, 2)] == "Day 1"
    rows_after_two_locations = len(worksheet.get_all_values())

    write_email_performance(client, target, month, "Strongsville", result)
    assert len(worksheet.get_all_values()) == rows_after_two_locations
