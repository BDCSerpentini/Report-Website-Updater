from pathlib import Path

from matador_reporting.reports.email_template_performance.config import EMAIL_CONFIGS
from matador_reporting.reports.email_template_performance.processor import EmailTemplatePerformanceProcessor


def test_orrville_october_exact_name_variants():
    # Fixture copied from the actual October 2026 Orrville export.
    csv_path = Path(__file__).parent / "fixtures" / "orrville_october_2026.csv"
    processor = EmailTemplatePerformanceProcessor(EMAIL_CONFIGS["Orrville"])
    result = processor.process_matador(csv_path)
    by_group = {row.reporting_group: row for row in result.campaigns}
    assert (by_group["Day 1"].emails_sent, by_group["Day 1"].emails_opened) == (505, 253)
    assert (by_group["Day 2"].emails_sent, by_group["Day 2"].emails_opened) == (454, 159)
    assert (by_group["Day 3"].emails_sent, by_group["Day 3"].emails_opened) == (438, 151)
    assert (by_group["Day 5"].emails_sent, by_group["Day 5"].emails_opened) == (420, 145)
    assert (by_group["Birthday"].emails_sent, by_group["Birthday"].emails_opened) == (28, 17)
    assert (by_group["KBB"].emails_sent, by_group["KBB"].emails_opened) == (11, 9)
    assert "- Auto Day 7 Internet Lead" in result.diagnostics.excluded_templates
    assert "Manual Email" in result.diagnostics.unmapped_templates


def test_orrville_mappings_do_not_change_medina():
    processor = EmailTemplatePerformanceProcessor(EMAIL_CONFIGS["Medina"])
    day1 = next(g for g in processor.config.groups if g.display_name == "Day 1")
    assert "-- # 1st Reply With Vehicle CRM Link" not in day1.templates
