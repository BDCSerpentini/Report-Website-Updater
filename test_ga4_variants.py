from pathlib import Path

from matador_reporting.reports.email_template_performance.ga4_parser import (
    parse_ga4_campaign_matrix,
)


FIXTURES = Path(__file__).parent / "fixtures"


def test_active_users_campaign_matrix_variant():
    result = parse_ga4_campaign_matrix(
        FIXTURES / "ga4_campaign_matrix_active_users.csv"
    )
    assert result.metadata.property_name == "Chevrolet - Strongsville"
    assert result.metadata.report_name == "Strongsville Reports-CTA Performance"
    assert result.user_metric == "Active users"
    assert result.total_unique_users == 283
    assert result.users_by_campaign["day_1"] == 110
    assert result.users_by_campaign["day_2"] == 68
    assert result.users_by_cta == {
        "used_inventory": 155,
        "new_inventory": 40,
        "homepage": 36,
        "specials": 30,
        "pre_approval": 18,
    }
