from matador_reporting.reports.email_template_performance.config import EMAIL_CONFIGS


def test_all_locations_are_available():
    assert tuple(EMAIL_CONFIGS) == (
        "Medina",
        "CDJR",
        "Strongsville",
        "Tallmadge",
        "Westlake",
        "Willoughby",
        "Orrville",
    )


def test_location_aliases_match_expected_report_labels():
    assert EMAIL_CONFIGS["CDJR"].matches_location("Serpentini CDJR North Olmsted")
    assert EMAIL_CONFIGS["CDJR"].matches_location("Chrysler Dodge Jeep Ram - North Olmsted")
    assert EMAIL_CONFIGS["Willoughby"].matches_location("Chevrolet - Willoughby Hills")
    assert EMAIL_CONFIGS["Orrville"].matches_location("Serpentini Chevrolet of Orrville")
    assert not EMAIL_CONFIGS["Westlake"].matches_location("Chevrolet - Medina")
