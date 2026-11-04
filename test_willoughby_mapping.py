from pathlib import Path

from matador_reporting.reports.email_template_performance import (
    EmailTemplatePerformanceProcessor,
)
from matador_reporting.reports.email_template_performance.config import EMAIL_CONFIGS


def test_willoughby_store_specific_templates():
    root = Path(__file__).parents[2]
    result = EmailTemplatePerformanceProcessor(EMAIL_CONFIGS["Willoughby"]).process(
        root / "upload" / "WH Template Performance(1).csv",
        root / "upload" / "WH Active vs Total(1).csv",
        root / "upload" / "WH Campaigns(1).csv",
    )
    campaigns = {item.ga4_campaign: item for item in result.campaigns}
    assert (campaigns["lease_renewal"].emails_sent, campaigns["lease_renewal"].emails_opened) == (21, 12)
    assert (campaigns["credit_app"].emails_sent, campaigns["credit_app"].emails_opened) == (23, 10)
    assert (campaigns["appointment"].emails_sent, campaigns["appointment"].emails_opened) == (3, 2)
    assert (campaigns["salesperson"].emails_sent, campaigns["salesperson"].emails_opened) == (21, 10)
    assert (campaigns["blank"].emails_sent, campaigns["blank"].emails_opened) == (2, 2)
    assert result.diagnostics.unmapped_templates == (
        "- Sales Rep Referrals Email",
        "Manual Email",
    )
