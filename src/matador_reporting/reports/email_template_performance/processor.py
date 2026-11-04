from __future__ import annotations

from pathlib import Path

from matador_reporting.core.contracts import UploadRequirement
from matador_reporting.core.errors import InvalidReportError
from matador_reporting.reports.email_template_performance.config import (
    MEDINA_EMAIL_CONFIG,
    EmailReportConfig,
)
from matador_reporting.reports.email_template_performance.models import (
    CampaignMetrics,
    EmailPerformanceResult,
    ProcessingDiagnostics,
    LocationMetrics,
)
from matador_reporting.reports.email_template_performance.ga4_parser import (
    parse_ga4_campaign_matrix,
    parse_ga4_summary,
)
from matador_reporting.reports.email_template_performance.parser import (
    parse_matador_email_performance,
)


class EmailTemplatePerformanceProcessor:
    report_type = "Email Template Performance"
    upload_requirements = (
        UploadRequirement("matador_email", "Email Template Performance Report CSV"),
        UploadRequirement("ga4_summary", "GA4 Email Performance CSV"),
        UploadRequirement("ga4_campaign", "GA4 Campaign Performance CSV"),
    )

    def __init__(self, config: EmailReportConfig = MEDINA_EMAIL_CONFIG) -> None:
        config.validate()
        self.config = config

    def validate_upload(self, upload_key: str, path: Path) -> None:
        if upload_key == "matador_email":
            metadata, _ = parse_matador_email_performance(path)
            location_text = metadata.dealership
        elif upload_key == "ga4_summary":
            location_text = parse_ga4_summary(path).metadata.property_name
        elif upload_key == "ga4_campaign":
            location_text = parse_ga4_campaign_matrix(path).metadata.property_name
        else:
            raise InvalidReportError(f"Unknown upload requirement: {upload_key}")
        if not self.config.matches_location(location_text):
            raise InvalidReportError(
                f"Expected {self.config.location}, found {location_text or 'no location'}"
            )

    def process(
        self,
        matador_path: Path,
        ga4_summary_path: Path,
        ga4_campaign_path: Path,
    ) -> EmailPerformanceResult:
        summary = parse_ga4_summary(ga4_summary_path)
        campaign_data = parse_ga4_campaign_matrix(ga4_campaign_path)
        self.validate_upload("ga4_summary", ga4_summary_path)
        self.validate_upload("ga4_campaign", ga4_campaign_path)

        if summary.metadata.period_start != campaign_data.metadata.period_start or summary.metadata.period_end != campaign_data.metadata.period_end:
            raise InvalidReportError("The two GA4 exports use different reporting periods")
        summary_control_users = (
            summary.total_users
            if campaign_data.user_metric == "Total users"
            else summary.active_users
        )
        configured_campaigns = {group.ga4_campaign for group in self.config.groups}
        unknown_campaigns = tuple(
            campaign for campaign in campaign_data.users_by_campaign if campaign not in configured_campaigns
        )
        cta_users = {
            campaign: campaign_data.users_by_campaign.get(campaign, 0)
            for campaign in configured_campaigns
        }
        result = self.process_matador(matador_path, cta_users)
        if result.metadata.period_start != summary.metadata.period_start or result.metadata.period_end != summary.metadata.period_end:
            raise InvalidReportError("Email Template Performance and GA4 exports use different reporting periods")

        warnings = list(result.diagnostics.warnings)
        matrix_total_users = campaign_data.total_unique_users
        if summary_control_users != matrix_total_users:
            difference = summary_control_users - matrix_total_users
            warnings.append(
                f"GA4 totals do not match: the summary reports {summary_control_users:,} "
                f"{campaign_data.user_metric}, while the Campaign × CTA matrix reports "
                f"{matrix_total_users:,} (difference: {difference:+,}). The matrix total "
                "was used for location CTA Users, CTR, and CTOR."
            )
        if campaign_data.user_metric == "Active users":
            warnings.append(
                "The GA4 campaign matrix does not contain Total users; campaign CTA Users were taken from Active users."
            )
        if unknown_campaigns:
            warnings.append(
                "GA4 contains campaigns that are not configured for this report; the location total may include their users."
            )
        campaign_instances = sum(campaign_data.users_by_campaign.values())
        if campaign_instances > matrix_total_users:
            warnings.append(
                "Campaign-level users overlap; do not sum campaign rows for the location unique-user total."
            )
        diagnostics = ProcessingDiagnostics(
            detected_templates=result.diagnostics.detected_templates,
            included_templates=result.diagnostics.included_templates,
            excluded_templates=result.diagnostics.excluded_templates,
            unmapped_templates=result.diagnostics.unmapped_templates,
            configured_but_missing_templates=result.diagnostics.configured_but_missing_templates,
            unmapped_ga4_campaigns=unknown_campaigns,
            warnings=tuple(warnings),
        )
        location = LocationMetrics(
            emails_sent=sum(item.emails_sent for item in result.campaigns),
            emails_opened=sum(item.emails_opened for item in result.campaigns),
            unique_cta_users=matrix_total_users,
            campaign_user_instances=campaign_instances,
        )
        return EmailPerformanceResult(result.metadata, result.campaigns, diagnostics, location)

    def process_matador(
        self,
        path: Path,
        cta_users_by_campaign: dict[str, int] | None = None,
    ) -> EmailPerformanceResult:
        metadata, frame = parse_matador_email_performance(path)
        if not self.config.matches_location(metadata.dealership):
            raise InvalidReportError(
                f"Expected {self.config.location}, found {metadata.dealership or 'no dealership'}"
            )

        cta_users_by_campaign = cta_users_by_campaign or {}
        detected = tuple(frame["eMail Template"].tolist())
        by_name: dict[str, dict[str, int | str]] = {}
        for row in frame.to_dict(orient="records"):
            name = str(row["eMail Template"])
            key = name.casefold()
            if key not in by_name:
                by_name[key] = {
                    "name": name,
                    "sent": 0,
                    "opened": 0,
                }
            by_name[key]["sent"] = int(by_name[key]["sent"]) + int(row["Emails Sent"])
            by_name[key]["opened"] = int(by_name[key]["opened"]) + int(row["Emails Opened"])

        excluded = tuple(
            name
            for name in detected
            if any(fragment.casefold() in name.casefold() for fragment in self.config.excluded_name_fragments)
        )
        excluded_keys = {name.casefold() for name in excluded}
        configured_keys = {
            template.casefold()
            for group in self.config.groups
            for template in group.templates
        }

        included: list[str] = []
        missing: list[str] = []
        campaigns: list[CampaignMetrics] = []
        for group in self.config.groups:
            sent = 0
            opened = 0
            for template in group.templates:
                key = template.casefold()
                if key not in by_name or key in excluded_keys:
                    missing.append(template)
                    continue
                row = by_name[key]
                sent += int(row["sent"])
                opened += int(row["opened"])
                included.append(str(row["name"]))

            campaigns.append(
                CampaignMetrics(
                    reporting_group=group.display_name,
                    ga4_campaign=group.ga4_campaign,
                    emails_sent=sent,
                    emails_opened=opened,
                    cta_users=cta_users_by_campaign.get(group.ga4_campaign),
                )
            )

        unmapped = tuple(
            name
            for name in detected
            if name.casefold() not in configured_keys and name.casefold() not in excluded_keys
        )
        diagnostics = ProcessingDiagnostics(
            detected_templates=detected,
            included_templates=tuple(included),
            excluded_templates=excluded,
            unmapped_templates=unmapped,
            configured_but_missing_templates=tuple(missing),
        )
        return EmailPerformanceResult(metadata, tuple(campaigns), diagnostics)
