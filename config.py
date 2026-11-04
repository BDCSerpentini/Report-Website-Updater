from __future__ import annotations

from dataclasses import dataclass

from matador_reporting.core.errors import ConfigurationError


@dataclass(frozen=True)
class CampaignGroup:
    display_name: str
    ga4_campaign: str
    templates: tuple[str, ...]


@dataclass(frozen=True)
class EmailReportConfig:
    location: str
    location_aliases: tuple[str, ...]
    excluded_name_fragments: tuple[str, ...]
    groups: tuple[CampaignGroup, ...]

    def matches_location(self, value: str) -> bool:
        normalized = value.casefold()
        return any(alias.casefold() in normalized for alias in self.location_aliases)

    def validate(self) -> None:
        assigned: dict[str, str] = {}
        for group in self.groups:
            if not group.templates:
                raise ConfigurationError(f"{group.display_name} has no templates")
            for template in group.templates:
                key = template.casefold()
                if key in assigned:
                    raise ConfigurationError(
                        f"Template {template!r} is assigned to both "
                        f"{assigned[key]!r} and {group.display_name!r}"
                    )
                assigned[key] = group.display_name


EMAIL_CAMPAIGN_GROUPS = (
        CampaignGroup(
            "Day 1",
            "day_1",
            (
                "- Vehicle Selected Phone Provided",
                "- Vehicle Selected No Phone",
                "- No Vehicle Phone Provided",
                "- No Vehicle No Phone",
            ),
        ),
        CampaignGroup("Day 2", "day_2", ("-- # Day 2", "- Day 2")),
        CampaignGroup("Day 3", "day_3", ("-- # Day 3", "- Day 3")),
        CampaignGroup("Day 5", "day_5", ("-- # Day 5", "- Day 5")),
        CampaignGroup("Day 7", "day_7", ("-- # Day 7", "- Day 7")),
        CampaignGroup(
            "Lease Renewal",
            "lease_renewal",
            (
                "1 Month Lease Renewal",
                "1 Month Lease WF",
                "2 Month Lease Renewal",
                "3 Month Lease Renewal",
                "3 Month Lease WF",
                "4 Month Lease Renewal",
                "4 Month Lease WF",
                "5 Month Lease Renewal",
                "5 Month Lease WF",
                "6 Months Lease Renewal",
                "6 Month Lease WF",
                "8 Month Lease Renewal",
                "8 Month Lease WF",
            ),
        ),
        CampaignGroup(
            "Anniversary", "anniversary", ("Happy 1st Anniversary WF",)
        ),
        CampaignGroup(
            "Credit App",
            "credit_app",
            ("- Capital 1", "- Credit App Pre-Approved"),
        ),
        CampaignGroup("KBB", "kbb", ("- KBB Elite",)),
        CampaignGroup(
            "Appointment",
            "appointment",
            (
                "- App Reminder",
                "- Appt Reminder",
                "- Appointment Reminder",
                "- Missed Appointment",
            ),
        ),
        CampaignGroup(
            "Salesperson",
            "salesperson",
            (
                "- # Salesperson SOLD Thank You",
                "- # Salesperson VISIT Thank You",
            ),
        ),
        CampaignGroup("Still Interested", "still_interested", ("- Still Interested?",)),
        CampaignGroup("Birthday", "birthday", ("Happy Birthday",)),
        CampaignGroup(
            "Blank",
            "blank",
            ("- BCD Blank", "- Blank BDC Template (eliteBDC)"),
        ),
        CampaignGroup("BDM Thank You", "bdm", ("- BDM Thank You",)),
)


def _location_config(location: str, *aliases: str) -> EmailReportConfig:
    return EmailReportConfig(
        location=location,
        location_aliases=aliases,
        excluded_name_fragments=("auto",),
        groups=EMAIL_CAMPAIGN_GROUPS,
    )


def _groups_with_additions(
    additions: dict[str, tuple[str, ...]],
) -> tuple[CampaignGroup, ...]:
    return tuple(
        CampaignGroup(
            display_name=group.display_name,
            ga4_campaign=group.ga4_campaign,
            templates=group.templates + additions.get(group.ga4_campaign, ()),
        )
        for group in EMAIL_CAMPAIGN_GROUPS
    )


WILLOUGHBY_EMAIL_CONFIG = EmailReportConfig(
    location="Willoughby",
    location_aliases=("Willoughby", "Willoughby Hills"),
    excluded_name_fragments=("auto",),
    groups=_groups_with_additions(
        {
            "lease_renewal": ("2 Month Lease WF",),
            "credit_app": ("- Credit App Received",),
            "salesperson": ("- Sales Rep Sold Thank You Email",),
            "blank": ("*Blank BDC Template (eliteBDC)",),
        }
    ),
)


EMAIL_CONFIGS = {
    "Medina": _location_config("Medina", "Medina"),
    "CDJR": EmailReportConfig(
        location="CDJR",
        location_aliases=("CDJR", "North Olmsted", "Chrysler Dodge Jeep Ram"),
        excluded_name_fragments=("auto",),
        groups=_groups_with_additions(
            {
                "day_1": (
                    "- Vehicle Slected No Phone",  # Actual CRM spelling
                    "- # Day 1",
                    "- Day 1",
                ),
                "day_2": ("- # Day 2",),
                "day_3": ("- # Day 3",),
                "day_5": ("- # Day 5",),
                "day_7": ("- # Day 7",),
                "birthday": ("-- # Birthday Email",),
                "credit_app": ("- Credit App Received",),
                "appointment": ("- # Appointment Reminder",),
                "blank": ("- BDC Blank",),
                "lease_renewal": (
                    "2 Month Lease Renewal (eliteBDC)",
                    "4 Month Lease Renewal (eliteBDC)",
                    "5 Month Lease Renewal (eliteBDC)",
                ),
                "kbb": ("KBB 2nd (eliteBDC)",),
            }
        ),
    ),
    "Strongsville": _location_config("Strongsville", "Strongsville"),
    "Tallmadge": _location_config("Tallmadge", "Tallmadge"),
    "Westlake": _location_config("Westlake", "Westlake"),
    "Willoughby": WILLOUGHBY_EMAIL_CONFIG,
    "Orrville": EmailReportConfig(
        location="Orrville",
        location_aliases=("Orrville",),
        excluded_name_fragments=("auto",),
        groups=_groups_with_additions(
            {
                "day_1": ("-- # 1st Reply With Vehicle CRM Link", "- Day 1"),
                "day_2": ("Day 2",),
                "day_3": ("Day 3",),
                "day_5": ("Day 5",),
                "birthday": ("-- # Birthday Email",),
                "kbb": ("- KBB Elite 1",),
                "anniversary": (
                    "Happy 1st Anniversary (eliteBDC)",
                    "Happy 2nd Anniversary WF",
                    "Happy 3rd Anniversary WF",
                    "Happy 4th Anniversary WF",
                    "Happy 5th Anniversary WF",
                ),
            }
        ),
    ),
}


MEDINA_EMAIL_CONFIG = EMAIL_CONFIGS["Medina"]
