from pathlib import Path

from matador_reporting.reports.email_template_performance import (
    EmailTemplatePerformanceProcessor,
)
from matador_reporting.reports.email_template_performance.config import EMAIL_CONFIGS


FIXTURES = Path(__file__).parent / "fixtures"


def test_mismatched_ga4_totals_use_matrix_and_warn():
    result = EmailTemplatePerformanceProcessor(EMAIL_CONFIGS["Westlake"]).process(
        FIXTURES / "westlake_email_performance.csv",
        FIXTURES / "westlake_ga4_summary.csv",
        FIXTURES / "westlake_ga4_campaign_matrix.csv",
    )
    assert result.location_metrics is not None
    assert result.location_metrics.unique_cta_users == 66
    warning = next(
        warning for warning in result.diagnostics.warnings
        if "GA4 totals do not match" in warning
    )
    assert "summary reports 70" in warning
    assert "matrix reports 66" in warning
    assert "difference: +4" in warning
    assert "matrix total was used" in warning.lower()
