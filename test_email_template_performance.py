from pathlib import Path

import pytest

from matador_reporting.reports.email_template_performance import (
    EmailTemplatePerformanceProcessor,
)
from matador_reporting.reports.email_template_performance.config import EMAIL_CONFIGS
from matador_reporting.reports.email_template_performance.parser import normalize_template_name


SAMPLE = Path(__file__).parent / "fixtures" / "medina_email_performance.csv"
GA4_SUMMARY = Path(__file__).parent / "fixtures" / "ga4_summary.csv"
GA4_CAMPAIGNS = Path(__file__).parent / "fixtures" / "ga4_campaign_matrix.csv"


@pytest.fixture(scope="module")
def result():
    processor = EmailTemplatePerformanceProcessor()
    return processor.process_matador(
        SAMPLE,
        cta_users_by_campaign={
            "day_1": 10,
            "day_2": 9,
            "day_3": 7,
            "day_5": 5,
            "day_7": 1,
            "lease_renewal": 1,
            "anniversary": 2,
            "credit_app": 1,
        },
    )


def campaign(result, name):
    return next(item for item in result.campaigns if item.reporting_group == name)


def test_strongsville_blank_template_alias_and_elead_equals_normalization():
    blank = next(
        group for group in EMAIL_CONFIGS["Strongsville"].groups if group.ga4_campaign == "blank"
    )
    assert "- Blank BDC Template (eliteBDC)" in blank.templates
    assert normalize_template_name("=- Blank BDC Template (eliteBDC)") == (
        "- Blank BDC Template (eliteBDC)"
    )


def test_metadata(result):
    assert result.metadata.dealership == "Serpentini Chevrolet of Medina"
    assert result.metadata.period_start.isoformat() == "2026-08-01"
    assert result.metadata.period_end.isoformat() == "2026-08-12"


def test_day_1_aggregation(result):
    day_1 = campaign(result, "Day 1")
    assert (day_1.emails_sent, day_1.emails_opened, day_1.cta_users) == (377, 110, 10)
    assert day_1.open_rate == pytest.approx(110 / 377)
    assert day_1.ctr == pytest.approx(10 / 377)
    assert day_1.ctor == pytest.approx(10 / 110)


def test_lease_includes_renewal_and_wf_variants(result):
    lease = campaign(result, "Lease Renewal")
    assert (lease.emails_sent, lease.emails_opened, lease.cta_users) == (18, 7, 1)


def test_auto_templates_are_excluded(result):
    assert set(result.diagnostics.excluded_templates) == {
        "- Auto Day 10 Internet Lead",
        "- Auto Day 30 Internet Lead",
        "- Auto Day 7 Internet Lead",
    }
    day_7 = campaign(result, "Day 7")
    assert (day_7.emails_sent, day_7.emails_opened) == (25, 10)


def test_percentages_are_recalculated_from_counts(result):
    credit = campaign(result, "Credit App")
    assert (credit.emails_sent, credit.emails_opened) == (9, 4)
    assert credit.open_rate == pytest.approx(4 / 9)


def test_complete_three_file_processing():
    result = EmailTemplatePerformanceProcessor().process(
        SAMPLE, GA4_SUMMARY, GA4_CAMPAIGNS
    )
    day_1 = campaign(result, "Day 1")
    assert day_1.cta_users == 10
    assert result.location_metrics is not None
    assert result.location_metrics.unique_cta_users == 31
    assert result.location_metrics.campaign_user_instances == 36
    assert result.location_metrics.cross_campaign_excess_user_instances == 5
    assert result.diagnostics.unmapped_ga4_campaigns == ()
    assert any("overlap" in warning for warning in result.diagnostics.warnings)
