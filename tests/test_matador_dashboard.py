from datetime import date

import pytest

import pandas as pd

from matador_reporting.app import _csv_download_data, _validate_selected_period
from matador_reporting.google_sheets import write_matador_dashboard
from matador_reporting.reports.matador_dashboard import MatadorDashboardProcessor


def _write(tmp_path, name, header, rows):
    path = tmp_path / name
    path.write_text("\n".join([header, *rows]), encoding="utf-8")
    return path


def _source(tmp_path, influenced_header="Appts Influenced"):
    engage = _write(
        tmp_path,
        "engage.csv",
        f"Start Date,End Date,Dealer,Customers Messaged,Customers Engaged,{influenced_header}",
        [
            "2026-07-01,2026-07-31,Serpentini Chevrolet of Medina,1000,400,100",
            "2026-07-01,2026-07-31,Serpentini Chevrolet of Strongsville,2000,900,200",
        ],
    )
    follow_up = _write(
        tmp_path,
        "follow.csv",
        f"Start Date,End Date,Dealer,{influenced_header}",
        [
            "2026-07-01,2026-07-31,Serpentini Chevrolet of Medina,20",
            "2026-07-01,2026-07-31,Serpentini Chevrolet of Strongsville,30",
        ],
    )
    reply = _write(
        tmp_path,
        "reply.csv",
        f"Start Date,End Date,Dealer,{influenced_header}",
        [
            "2026-07-01,2026-07-31,Serpentini Chevrolet of Medina,40",
            "2026-07-01,2026-07-31,Serpentini Chevrolet of Strongsville,50",
        ],
    )
    return MatadorDashboardProcessor().process_sources(engage, follow_up, reply)


def test_dashboard_calculations(tmp_path):
    processor = MatadorDashboardProcessor()
    source = _source(tmp_path)
    result = processor.build_result(source, {"Medina": 500, "Strongsville": 800})

    medina = result.locations[0]
    assert medina.leads == 1000
    assert medina.engaged_contacts == 400
    assert medina.ai_influenced_appointments == 160
    assert medina.lead_to_engaged == 0.4
    assert medina.lead_to_appointment == 0.5
    assert medina.ai_appointment_percent == 0.32
    assert result.totals.leads == 3000
    assert result.totals.total_appointments == 1300
    assert result.totals.ai_influenced_appointments == 440


def test_dashboard_accepts_ai_influenced_appts_column_name(tmp_path):
    source = _source(tmp_path, "AI Influenced Appts")
    result = MatadorDashboardProcessor().build_result(
        source,
        {"Medina": 500, "Strongsville": 800},
    )
    assert result.locations[0].ai_influenced_appointments == 160
    assert result.totals.ai_influenced_appointments == 440


def test_selected_month_safeguard_rejects_wrong_period():
    with pytest.raises(ValueError, match="Nothing was generated or exported"):
        _validate_selected_period(
            date(2026, 8, 1),
            date(2026, 7, 1),
            date(2026, 7, 31),
        )
    with pytest.raises(ValueError, match="Nothing was generated or exported"):
        _validate_selected_period(
            date(2026, 8, 1),
            date(2026, 8, 1),
            date(2026, 9, 1),
        )


def test_csv_download_formats_percentages_for_excel():
    data = _csv_download_data(
        pd.DataFrame({"Location": ["Medina", "Orrville"], "Rate": [0.1234, None]}),
        ("Rate",),
    )
    text = data.decode("utf-8-sig")
    assert "Medina,12.34%" in text
    assert "Orrville," in text

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
        self.col_count = 90
        self.batch_value_options = []

    def _write(self, range_name, values):
        import re
        match = re.fullmatch(r"([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?", range_name)
        start_column = _column_number(match.group(1))
        start_row = int(match.group(2))
        for row_offset, row in enumerate(values):
            for column_offset, value in enumerate(row):
                self.grid[(start_row + row_offset, start_column + column_offset)] = value

    def update(self, range_name=None, values=None): self._write(range_name, values)
    def batch_update(self, updates, value_input_option=None):
        self.batch_value_options.append(
            (tuple(update["range"] for update in updates), value_input_option)
        )
        for update in updates: self._write(update["range"], update["values"])
    def get_all_values(self):
        if not self.grid: return []
        last_row = max(row for row, _column in self.grid)
        last_column = max(column for _row, column in self.grid)
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


def test_dashboard_google_sheets_month_block(tmp_path):
    processor = MatadorDashboardProcessor()
    result = processor.build_result(_source(tmp_path), {"Medina": 500, "Strongsville": 800})
    client = FakeClient()

    write = write_matador_dashboard(client, "abcdefghijklmnopqrstuvwxyz123", date(2026, 7, 1), result)
    worksheet = client.spreadsheet.worksheets["Matador Dashboard"]
    assert write.updated_rows == 3
    assert worksheet.grid[(1, 2)] == "JULY 2026"
    assert worksheet.grid[(1, 9)] == "AUGUST 2026"
    assert worksheet.grid[(1, 16)] == "SEPTEMBER 2026"
    assert (1, 23) not in worksheet.grid
    assert worksheet.grid[(3, 2)] == 1000
    assert worksheet.grid[(3, 5)] == 500
    assert worksheet.grid[(3, 7)] == 160
    assert worksheet.grid[(10, 2)] == 3000
    assert worksheet.grid[(12, 1)] == "MONTH-OVER-MONTH COMPARISON — Previous month unavailable in this quarter"
    border = client.spreadsheet.batch_calls[-1]["requests"][0]["updateBorders"]
    assert border["range"]["startColumnIndex"] == 1
    assert border["range"]["endColumnIndex"] == 8

    write_matador_dashboard(client, "abcdefghijklmnopqrstuvwxyz123", date(2026, 7, 1), result)
    assert worksheet.grid[(3, 2)] == 1000


def test_dashboard_builds_four_metric_month_over_month_comparison(tmp_path):
    processor = MatadorDashboardProcessor()
    result = processor.build_result(_source(tmp_path), {"Medina": 500, "Strongsville": 800})
    client = FakeClient()
    target = "abcdefghijklmnopqrstuvwxyz123"

    write_matador_dashboard(client, target, date(2026, 7, 1), result)
    write_matador_dashboard(client, target, date(2026, 8, 1), result)
    worksheet = client.spreadsheet.worksheets["Matador Dashboard"]

    assert worksheet.grid[(12, 1)] == "LEADS — JULY 2026 VS AUGUST 2026"
    assert worksheet.grid[(14, 1)] == "Medina"
    assert worksheet.grid[(14, 2)] == '=IF(B3="","",B3)'
    assert worksheet.grid[(14, 3)] == '=IF(I3="","",I3)'
    assert worksheet.grid[(14, 4)] == '=IF(OR(B3="",I3=""),"",I3-B3)'
    assert worksheet.grid[(14, 5)] == '=IFERROR(IF(OR(B3="",I3=""),"",(I3-B3)/B3),"")'

    assert worksheet.grid[(12, 7)] == "APPOINTMENTS — JULY 2026 VS AUGUST 2026"
    assert worksheet.grid[(14, 8)] == '=IF(E3="","",E3)'
    assert worksheet.grid[(14, 9)] == '=IF(L3="","",L3)'

    assert worksheet.grid[(23, 1)] == "LEAD → APPOINTMENT RATE — JULY 2026 VS AUGUST 2026"
    assert worksheet.grid[(25, 2)] == '=IF(F3="","",F3)'
    assert worksheet.grid[(25, 3)] == '=IF(M3="","",M3)'
    assert worksheet.grid[(25, 4)] == '=IF(OR(F3="",M3=""),"",M3-F3)'

    assert worksheet.grid[(23, 7)] == "AI APPT % — JULY 2026 VS AUGUST 2026"
    assert worksheet.grid[(25, 8)] == '=IF(H3="","",H3)'
    assert worksheet.grid[(25, 9)] == '=IF(O3="","",O3)'
    assert worksheet.grid[(25, 10)] == '=IF(OR(H3="",O3=""),"",O3-H3)'
    assert worksheet.grid[(21, 1)] == "Total"
    assert worksheet.grid[(32, 7)] == "Total"
    assert (("A14:E21",), "USER_ENTERED") in worksheet.batch_value_options
    assert (("G14:K21",), "USER_ENTERED") in worksheet.batch_value_options
    assert (("A25:D32",), "USER_ENTERED") in worksheet.batch_value_options
    assert (("G25:J32",), "USER_ENTERED") in worksheet.batch_value_options


def test_dashboard_switches_to_selected_quarter(tmp_path):
    processor = MatadorDashboardProcessor()
    result = processor.build_result(_source(tmp_path), {"Medina": 500, "Strongsville": 800})
    client = FakeClient()
    target = "abcdefghijklmnopqrstuvwxyz123"

    write_matador_dashboard(client, target, date(2026, 1, 1), result)
    worksheet = client.spreadsheet.worksheets["Matador Dashboard"]
    assert worksheet.grid[(1, 2)] == "JANUARY 2026"

    write_matador_dashboard(client, target, date(2026, 7, 1), result)
    assert worksheet.grid[(1, 2)] == "JULY 2026"
    assert all(value != "JANUARY 2026" for value in worksheet.grid.values())
