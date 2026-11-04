from pathlib import Path

from matador_reporting.reports.email_template_performance.ga4_parser import (
    parse_ga4_summary,
)


FIXTURES = Path(__file__).parent / "fixtures"


def test_summary_with_campaign_details_uses_grand_total():
    summary = parse_ga4_summary(
        FIXTURES / "willoughby_ga4_summary_with_campaigns.csv"
    )
    assert summary.metadata.property_name == "Chevrolet - Willoughby Hills"
    assert summary.total_users == 151
    assert summary.active_users == 150
    assert summary.sessions == 238
