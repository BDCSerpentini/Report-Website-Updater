from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class SourceMetadata:
    dealership: str
    generated_text: str
    period_start: date
    period_end: date


@dataclass(frozen=True)
class GA4Metadata:
    property_name: str
    report_name: str
    period_start: date
    period_end: date


@dataclass(frozen=True)
class GA4Summary:
    metadata: GA4Metadata
    total_users: int
    active_users: int
    sessions: int


@dataclass(frozen=True)
class GA4CampaignData:
    metadata: GA4Metadata
    total_unique_users: int
    users_by_campaign: dict[str, int]
    users_by_cta: dict[str, int]
    user_metric: str = "Total users"


@dataclass(frozen=True)
class CampaignMetrics:
    reporting_group: str
    ga4_campaign: str
    emails_sent: int
    emails_opened: int
    cta_users: int | None

    @property
    def open_rate(self) -> float | None:
        return self.emails_opened / self.emails_sent if self.emails_sent else None

    @property
    def ctr(self) -> float | None:
        if self.cta_users is None or not self.emails_sent:
            return None
        return self.cta_users / self.emails_sent

    @property
    def ctor(self) -> float | None:
        if self.cta_users is None or not self.emails_opened:
            return None
        return self.cta_users / self.emails_opened


@dataclass(frozen=True)
class ProcessingDiagnostics:
    detected_templates: tuple[str, ...]
    included_templates: tuple[str, ...]
    excluded_templates: tuple[str, ...]
    unmapped_templates: tuple[str, ...]
    configured_but_missing_templates: tuple[str, ...]
    unmapped_ga4_campaigns: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class LocationMetrics:
    emails_sent: int
    emails_opened: int
    unique_cta_users: int
    campaign_user_instances: int

    @property
    def open_rate(self) -> float | None:
        return self.emails_opened / self.emails_sent if self.emails_sent else None

    @property
    def ctr(self) -> float | None:
        return self.unique_cta_users / self.emails_sent if self.emails_sent else None

    @property
    def ctor(self) -> float | None:
        return self.unique_cta_users / self.emails_opened if self.emails_opened else None

    @property
    def cross_campaign_excess_user_instances(self) -> int:
        return max(0, self.campaign_user_instances - self.unique_cta_users)


@dataclass(frozen=True)
class EmailPerformanceResult:
    metadata: SourceMetadata
    campaigns: tuple[CampaignMetrics, ...]
    diagnostics: ProcessingDiagnostics
    location_metrics: LocationMetrics | None = None
