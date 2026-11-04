from matador_reporting.reports.lead_source_performance import LeadSourcePerformanceProcessor
from matador_reporting.core.errors import InvalidReportError
from matador_reporting.app import _lead_source_frame

import pytest


def test_top_15_is_selected_dynamically_by_leads(tmp_path):
    header = "Start Date,End Date,Lead Source,Dealers,Leads,Engaged Leads,AI Influenced Appointments,User Appointments,AI Appointments,AI Looped Your Team In"
    rows = [
        f"2026-07-01,2026-07-31,Source {index:02d},6,{index * 10},{index},1,0,1,2"
        for index in range(1, 18)
    ]
    path = tmp_path / "lead_sources.csv"
    path.write_text("\n".join([header, *rows]), encoding="utf-8")
    result = LeadSourcePerformanceProcessor().process(path)

    assert len(result.top_sources) == 15
    assert result.top_sources[0].lead_source == "Source 17"
    assert result.top_sources[0].leads == 170
    assert result.top_sources[-1].lead_source == "Source 03"
    assert result.top_sources[-1].rank == 15
    assert result.all_source_count == 17
    frame = _lead_source_frame(result)
    total = frame.iloc[-1]
    assert total["Lead Source"] == "Top 15 Total"
    assert total["Leads"] == sum(item.leads for item in result.top_sources)
    assert total["Engagement Rate"] == pytest.approx(
        sum(item.engaged_leads for item in result.top_sources)
        / sum(item.leads for item in result.top_sources)
    )


def test_individual_location_reports_are_combined_by_lead_source(tmp_path):
    header = "Start Date,End Date,Lead Source,Dealers,Leads,Engaged Leads,AI Influenced Appointments,User Appointments,AI Appointments,AI Looped Your Team In"
    medina = tmp_path / "medina.csv"
    medina.write_text(
        "\n".join([header, "2026-07-01,2026-07-31,AutoTrader,1,100,40,10,8,5,2"]),
        encoding="utf-8",
    )
    westlake = tmp_path / "westlake.csv"
    westlake.write_text(
        "\n".join([
            header,
            "2026-07-01,2026-07-31,autotrader,1,70,30,8,6,4,1",
            "2026-07-01,2026-07-31,KBB,1,50,25,5,4,3,2",
        ]),
        encoding="utf-8",
    )

    result = LeadSourcePerformanceProcessor().process_many([medina, westlake])

    assert result.all_source_count == 2
    assert result.all_leads == 220
    assert result.top_sources[0].lead_source == "AutoTrader"
    assert result.top_sources[0].dealers == 2
    assert result.top_sources[0].leads == 170
    assert result.top_sources[0].engaged_leads == 70


def test_individual_location_reports_reject_mixed_months(tmp_path):
    header = "Start Date,End Date,Lead Source,Dealers,Leads,Engaged Leads,AI Influenced Appointments,User Appointments,AI Appointments,AI Looped Your Team In"
    july = tmp_path / "july.csv"
    july.write_text("\n".join([header, "2026-07-01,2026-07-31,KBB,1,10,5,1,1,1,0"]), encoding="utf-8")
    august = tmp_path / "august.csv"
    august.write_text("\n".join([header, "2026-08-01,2026-08-31,KBB,1,10,5,1,1,1,0"]), encoding="utf-8")

    with pytest.raises(InvalidReportError, match="conflicting reporting periods"):
        LeadSourcePerformanceProcessor().process_many([july, august])


def test_october_2026_export_is_accepted():
    from pathlib import Path
    import os
    sample = os.environ.get("MATADOR_OCTOBER_CSV")
    if not sample:
        pytest.skip("Provide MATADOR_OCTOBER_CSV for October export regression")
    result = LeadSourcePerformanceProcessor().process(Path(sample))
    assert (result.period_start.isoformat(), result.period_end.isoformat()) == ("2026-10-01", "2026-10-31")
    assert result.all_source_count == 138
    assert result.all_leads == 7978
    assert result.top_sources[0].ai_influenced_appointments >= 0
    frame = _lead_source_frame(result)
    assert "AI Influenced Appointments" in frame.columns
    assert "AI Influenced Appointment Rate" in frame.columns
