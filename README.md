# Reporting Dashboard

Modular Python reporting application with separate Email Template Performance and Matador Dashboard pages.

The current version contains:

- a reusable report registry;
- strict CSV validation and metadata extraction;
- the Medina Email Template Performance mapping;
- parsing and validation for the GA4 summary and Campaign × CTA exports;
- aggregation by GA4/UTM campaign group;
- recalculation of Open Rate, CTR, and CTOR from underlying counts;
- location-level unique-user reconciliation without adding overlapping campaign users;
- diagnostics for excluded, unmapped, and missing templates.
- a styled Streamlit upload and report-preview interface.
- idempotent quarterly Google Sheets export using a service account.
- selectable location configurations for Medina, CDJR, Strongsville, Tallmadge,
  Westlake, Willoughby, and Orrville.

## Run the application

Create and activate a virtual environment, then install the project:

```bash
python -m pip install -e .
streamlit run app.py
```

The current sample report can be checked with:

```bash
python -m pytest
```

## Google Sheets configuration

Keep your existing service-account values under `[google_service_account]` in
`.streamlit/secrets.toml`. Optionally save a default destination spreadsheet:

```toml
[google_sheets]
spreadsheet_url = "https://docs.google.com/spreadsheets/d/YOUR_SPREADSHEET_ID/edit"
```

Share that spreadsheet with the `client_email` from your service-account section.
The app creates or updates the `Email Template Performance` tab; uploading the
same location and month again replaces that month's values instead of adding duplicate rows.

The interface includes a copyable service-account email reminder for brand-new
spreadsheets. Previously shared spreadsheets do not need to be shared again.

The seven locations currently share the confirmed Medina template-to-UTM mapping.
Any store-specific template names are surfaced as unmapped in the preview so they
can be added explicitly without guessing.

## Matador Dashboard

Use the sidebar to open the separate `Matador Dashboard` page. Upload the three
per-dealer exports for AI Engage, AI Follow-Up, and AI Reply, then
enter each location's total appointments for the reporting period. The app
calculates Lead → Engaged, Lead → Appointment Rate, and AI Appt % by location.

AI Influenced Appointments is the sum of `Appts Influenced` or
`AI Influenced Appts` from the three source reports. The Google Sheets export writes only the three monthly blocks in the
selected reporting quarter to the `Matador Dashboard` tab. The destination can
be the same spreadsheet used by Email Template
Performance or a different spreadsheet URL.

The Matador Dashboard tab also builds a month-over-month comparison beneath the
quarterly blocks for Leads, Appointments, Lead → Appointment Rate, and AI Appt %.
Count metrics show the numerical difference and percent change. Rate metrics show
the percentage-point change. The first month of each quarter displays that no
previous month is available within the current quarterly tab.

All report pages use separate Month and Year dropdowns. Processing stops if
the source reporting periods differ from one another or do not match the selected
month and year, preventing data from being written into the wrong monthly block.

## Lead Source Performance

The Lead Source Performance page accepts either one monthly Lead Sources CSV
containing every location or separate CSV uploads for individual locations.
Separate files are combined by lead source before the report dynamically
selects the 15 highest-volume sources by `Leads`. Mixed reporting periods are
rejected. Each reporting
month keeps its own ranked list, so sources can enter or leave the top 15 from
month to month. The quarterly Google Sheets tab is named `Lead Source Performance`.

Every report preview includes a `Download Results CSV` button. Downloaded files
include the reporting month and display calculated rates as readable percentages.

## Volie SMS Service Appointments

Upload one GA4 Service Reports-SMS Event Tracking CSV for each available location.
The report extracts Active Users from either `form_submission_service_appt` or
`asc_form_submission_service_appt`, displays each uploaded location and a combined
total, and records the partial-month reporting end date. Missing event rows are
shown as zero with a visible warning. The Google Sheets tab is named
`Volie SMS Service Appointments` and is organized by reporting quarter.
An optional Bitly Links by Clicks CSV adds Schedule Service clicks, including
the Orrville Scheduler and CDJR/CDRJ Scheduler naming variants. The report then
calculates `GA4 Active Users ÷ Bitly Clicks` by location and overall. Locations
without both sources remain visible but are excluded from the comparable total.

GA4 campaign matrices may use either Total Users or the expanded Active Users,
Sessions, Key Events layout. Total Users is preferred; Active Users is used only
when Total Users is absent, with a visible warning in the report preview.

If the GA4 summary and Campaign × CTA matrix grand totals differ, processing
continues with a prominent reconciliation warning. The matrix grand total is used
for location CTA Users, CTR, and CTOR because it represents the attributable
campaign population.

Willoughby has a store-specific template mapping for its Appointment Reminder,
Credit App Received, Sales Rep Sold Thank You, eliteBDC Blank, and 2 Month Lease
WF names, based on the Willoughby UTM reference file.

Review and social-media links are intentionally outside this report. App,
Appt, and Appointment Reminder template-name variants are combined in the
single Appointment reporting group.

GA4 summary exports may contain campaign detail rows. When an explicit Grand
total row is present, that row is used for reconciliation and the detail rows
are not mistaken for conflicting totals.
