from pathlib import Path
from matador_reporting.reports.email_template_performance.config import EMAIL_CONFIGS
from matador_reporting.reports.email_template_performance.processor import EmailTemplatePerformanceProcessor


def test_cdjr_mapping_october_export():
    csv_path = Path(__file__).resolve().parent / "fixtures" / "cdjr_oct_2026.csv"
    result = EmailTemplatePerformanceProcessor(EMAIL_CONFIGS["CDJR"]).process_matador(csv_path)
    groups = {r.reporting_group: r for r in result.campaigns}
    assert (groups["Day 1"].emails_sent, groups["Day 1"].emails_opened) == (810, 323)
    assert (sum(r.emails_sent for r in result.campaigns), sum(r.emails_opened for r in result.campaigns)) == (3307, 1202)
    assert set(result.diagnostics.unmapped_templates) == {"- Equity Email", "Manual Email", "LT - 3mo Lease Termination"}


def test_cdjr_does_not_change_other_locations():
    from matador_reporting.reports.email_template_performance.config import EMAIL_CONFIGS
    cdjr = {g.display_name: g.templates for g in EMAIL_CONFIGS["CDJR"].groups}
    medina = {g.display_name: g.templates for g in EMAIL_CONFIGS["Medina"].groups}
    orrville = {g.display_name: g.templates for g in EMAIL_CONFIGS["Orrville"].groups}
    assert "- Vehicle Slected No Phone" in cdjr["Day 1"]
    assert "- Vehicle Slected No Phone" not in medina["Day 1"]
    assert "-- # 1st Reply With Vehicle CRM Link" in orrville["Day 1"]
