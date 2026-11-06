from __future__ import annotations

import calendar
import hashlib
import json
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from matador_reporting.core.errors import ReportError
from matador_reporting.reports.bdc_agents.ui import manage_page as _bdc_manage_page, report_page as _bdc_report_page
from matador_reporting.github_publisher import PublishError, publish_report, serialize_report, reporting_month_key
from matador_reporting.google_sheets import (
    service_account_client,
    write_email_performance,
    write_lead_source_performance,
    write_matador_dashboard,
    write_volie_sms_service_appointments,
)
from matador_reporting.reports.email_template_performance import (
    EmailTemplatePerformanceProcessor,
)
from matador_reporting.reports.email_template_performance.config import EMAIL_CONFIGS
from matador_reporting.reports.email_template_performance.models import (
    EmailPerformanceResult,
)
from matador_reporting.reports.matador_dashboard import (
    MatadorDashboardProcessor,
    MatadorDashboardResult,
)
from matador_reporting.reports.lead_source_performance import (
    LeadSourcePerformanceProcessor,
    LeadSourcePerformanceResult,
)
from matador_reporting.reports.volie_sms_service_appointments import (
    VolieSmsServiceAppointmentsProcessor,
    VolieSmsServiceAppointmentsResult,
)


REPORT_TYPE = "Email Template Performance"
LOCATIONS = tuple(EMAIL_CONFIGS)
GOOGLE_SERVICE_ACCOUNT_EMAIL = "volie-report-automation@volie-report-automation.iam.gserviceaccount.com"
MONTH_NAMES = tuple(calendar.month_name[1:])


def _configure_page() -> None:
    st.set_page_config(
        page_title="Reporting Dashboard",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(
        """
        <style>
        .stApp { background: #f4f6fb; color: #172033; }
        .block-container { max-width: 1380px; padding-top: 2.25rem; padding-bottom: 4rem; }
        .matador-hero {
            padding: 1.75rem 2rem; border-radius: 22px;
            background: linear-gradient(120deg, #17233c 0%, #253f77 58%, #596de1 100%);
            color: white; box-shadow: 0 18px 45px rgba(30, 48, 88, .18);
            margin-bottom: 1.25rem;
        }
        .matador-hero h1 { margin: 0; font-size: 2.15rem; letter-spacing: -.04em; }
        .matador-hero p { margin: .45rem 0 0; color: #dce5ff; font-size: 1rem; }
        .section-label { color: #596579; font-size: .78rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
        div[data-testid="stMetric"] {
            background: white; border: 1px solid #e2e7f1; padding: 1rem 1.1rem;
            border-radius: 15px; box-shadow: 0 5px 16px rgba(36, 53, 84, .05);
        }
        div[data-testid="stFileUploader"] section {
            background: white; border: 1px dashed #aab6cf; border-radius: 14px;
        }
        div[data-testid="stDataFrame"] { border: 1px solid #e2e7f1; border-radius: 14px; overflow: hidden; }
        .status-line { color: #5e6b82; font-size: .9rem; margin-top: -.35rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{value:.2%}"


def _friendly_date(value: date) -> str:
    return f"{value:%B} {value.day}, {value.year}"


def _short_date(value: date) -> str:
    return f"{value:%b} {value.day}"


def _month_year_selector(key_prefix: str) -> date:
    today = date.today()
    month_column, year_column = st.columns(2)
    month_name = month_column.selectbox(
        "Month",
        MONTH_NAMES,
        index=today.month - 1,
        key=f"{key_prefix}_month",
    )
    years = tuple(range(today.year + 1, 2019, -1))
    year = year_column.selectbox(
        "Year",
        years,
        index=years.index(today.year),
        key=f"{key_prefix}_year",
    )
    return date(int(year), MONTH_NAMES.index(month_name) + 1, 1)


def _validate_selected_period(reporting_month: date, period_start: date, period_end: date) -> None:
    selected = (reporting_month.year, reporting_month.month)
    if (period_start.year, period_start.month) != selected or (period_end.year, period_end.month) != selected:
        raise ValueError(
            f"Selected month is {reporting_month:%B %Y}, but the uploaded reports cover "
            f"{period_start:%B %d, %Y}–{period_end:%B %d, %Y}. Nothing was generated or exported."
        )


def _save_upload(upload, directory: Path, filename: str) -> Path:
    path = directory / filename
    path.write_bytes(upload.getvalue())
    return path


def _default_spreadsheet_target() -> str:
    try:
        return str(st.secrets.get("google_sheets", {}).get("spreadsheet_url", ""))
    except Exception:
        return ""


def _csv_download_data(frame: pd.DataFrame, percent_columns: tuple[str, ...]) -> bytes:
    export = frame.copy()
    for column in percent_columns:
        if column in export.columns:
            export[column] = export[column].map(
                lambda value: "" if pd.isna(value) else f"{float(value):.2%}"
            )
    return export.to_csv(index=False).encode("utf-8-sig")


def _campaign_frame(result: EmailPerformanceResult) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Template / Campaign": item.reporting_group,
                "UTM Campaign": item.ga4_campaign,
                "Sent": item.emails_sent,
                "Opens": item.emails_opened,
                "Open Rate": item.open_rate,
                "CTA Users": item.cta_users,
                "CTR": item.ctr,
                "CTOR": item.ctor,
            }
            for item in result.campaigns
            if item.emails_sent or item.emails_opened or item.cta_users
        ]
    )


def _render_summary(result: EmailPerformanceResult) -> None:
    metrics = result.location_metrics
    if metrics is None:
        return

    st.markdown('<p class="section-label">Location summary</p>', unsafe_allow_html=True)
    columns = st.columns(7)
    values = (
        ("Emails Sent", f"{metrics.emails_sent:,}"),
        ("Emails Opened", f"{metrics.emails_opened:,}"),
        ("Open Rate", _percent(metrics.open_rate)),
        ("Unique CTA Users", f"{metrics.unique_cta_users:,}"),
        ("CTR", _percent(metrics.ctr)),
        ("CTOR", _percent(metrics.ctor)),
        ("Templates Included", f"{len(result.diagnostics.included_templates):,}"),
    )
    for column, (label, value) in zip(columns, values):
        column.metric(label, value)

    start = _friendly_date(result.metadata.period_start)
    end = _friendly_date(result.metadata.period_end)
    st.markdown(
        f'<p class="status-line">Source period: {start}–{end} · {result.metadata.dealership}</p>',
        unsafe_allow_html=True,
    )


def _render_diagnostics(result: EmailPerformanceResult, reporting_month: date) -> None:
    last_day = calendar.monthrange(reporting_month.year, reporting_month.month)[1]
    metadata = result.metadata
    if metadata.period_start.year != reporting_month.year or metadata.period_start.month != reporting_month.month:
        st.error("The selected reporting month does not match the uploaded files.")
    elif metadata.period_start.day != 1 or metadata.period_end.day != last_day:
        st.info(
            f"Partial-month report: these files cover {_short_date(metadata.period_start)}–{_short_date(metadata.period_end)}, "
            f"not the complete month ending {reporting_month:%b} {last_day}."
        )

    for warning in result.diagnostics.warnings:
        st.warning(warning)

    with st.expander("Processing details", expanded=False):
        a, b, c = st.columns(3)
        a.metric("Templates detected", len(result.diagnostics.detected_templates))
        b.metric("Templates included", len(result.diagnostics.included_templates))
        c.metric("Templates excluded", len(result.diagnostics.excluded_templates))

        if result.diagnostics.excluded_templates:
            st.markdown("**Excluded by rule**")
            st.write(list(result.diagnostics.excluded_templates))
        if result.diagnostics.unmapped_templates:
            st.markdown("**Detected but not configured**")
            st.write(list(result.diagnostics.unmapped_templates))
        if result.diagnostics.unmapped_ga4_campaigns:
            st.markdown("**GA4 campaigns not configured**")
            st.write(list(result.diagnostics.unmapped_ga4_campaigns))
        if result.diagnostics.configured_but_missing_templates:
            st.markdown("**Configured templates not present in this upload**")
            st.caption("This is informational; a template may simply have had no activity during the period.")
            st.write(list(result.diagnostics.configured_but_missing_templates))


def _email_template_page() -> None:
    st.markdown(
        """
        <div class="matador-hero">
          <h1>Email Template Performance</h1>
          <p>Combine email template performance with GA4 campaign attribution.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<p class="section-label">Report setup</p>', unsafe_allow_html=True)
    setup_1, setup_2, setup_3, setup_4 = st.columns([1.3, 1, 1, 1])
    report_type = setup_1.selectbox("Report Type", (REPORT_TYPE,))
    location = setup_2.selectbox("Location", LOCATIONS)
    with setup_3:
        month_name = st.selectbox("Month", MONTH_NAMES, index=date.today().month - 1, key="email_month")
    with setup_4:
        years = tuple(range(date.today().year + 1, 2019, -1))
        selected_year = st.selectbox("Year", years, index=years.index(date.today().year), key="email_year")
    reporting_month = date(int(selected_year), MONTH_NAMES.index(month_name) + 1, 1)
    if (st.session_state.get("reporting_month") not in (None, reporting_month)
            or st.session_state.get("location") not in (None, location)):
        st.session_state.pop("report_result", None)

    st.markdown('<p class="section-label">Upload source reports</p>', unsafe_allow_html=True)
    upload_1, upload_2, upload_3 = st.columns(3)
    matador_upload = upload_1.file_uploader(
        "Email Template Performance Report",
        type=("csv",),
        key="matador_email",
    )
    ga4_summary_upload = upload_2.file_uploader(
        "GA4 Active and Unique Users",
        type=("csv",),
        key="ga4_summary",
    )
    ga4_campaign_upload = upload_3.file_uploader(
        "GA4 Campaign × CTA Matrix",
        type=("csv",),
        key="ga4_campaign",
    )

    ready = all((matador_upload, ga4_summary_upload, ga4_campaign_upload))
    generate = st.button(
        "Generate Report",
        type="primary",
        use_container_width=True,
        disabled=not ready,
    )
    if not ready:
        st.caption("Upload all three CSV reports to generate the preview.")
    st.caption("Safety check: all uploaded reporting periods must match the selected month and year.")

    if generate:
        processor = EmailTemplatePerformanceProcessor(EMAIL_CONFIGS[location])
        try:
            with tempfile.TemporaryDirectory(prefix="matador-reporting-") as temp_name:
                directory = Path(temp_name)
                matador_path = _save_upload(matador_upload, directory, "matador.csv")
                summary_path = _save_upload(ga4_summary_upload, directory, "ga4_summary.csv")
                campaigns_path = _save_upload(ga4_campaign_upload, directory, "ga4_campaigns.csv")
                result = processor.process(
                    matador_path, summary_path, campaigns_path
                )
                _validate_selected_period(
                    reporting_month,
                    result.metadata.period_start,
                    result.metadata.period_end,
                )
                st.session_state["report_result"] = result
                st.session_state["reporting_month"] = reporting_month
                st.session_state["report_type"] = report_type
                st.session_state["location"] = location
        except (ReportError, ValueError) as exc:
            st.session_state.pop("report_result", None)
            st.error(str(exc))

    result = st.session_state.get("report_result")
    if result is not None:
        st.divider()
        st.subheader(f"{st.session_state['location']} · {st.session_state['reporting_month']:%B %Y}")
        _render_summary(result)
        _render_diagnostics(result, st.session_state["reporting_month"])

        st.markdown('<p class="section-label">Campaign performance</p>', unsafe_allow_html=True)
        frame = _campaign_frame(result)
        st.dataframe(
            frame,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Sent": st.column_config.NumberColumn(format="localized"),
                "Opens": st.column_config.NumberColumn(format="localized"),
                "CTA Users": st.column_config.NumberColumn(format="localized"),
                "Open Rate": st.column_config.NumberColumn(format="percent"),
                "CTR": st.column_config.NumberColumn(format="percent"),
                "CTOR": st.column_config.NumberColumn(format="percent"),
            },
        )
        email_export = frame.copy()
        email_export.insert(0, "Location", st.session_state["location"])
        email_export.insert(1, "Reporting Month", st.session_state["reporting_month"].strftime("%B %Y"))
        st.download_button(
            "Download Results CSV",
            data=_csv_download_data(email_export, ("Open Rate", "CTR", "CTOR")),
            file_name=f"email-template-performance-{st.session_state['location'].lower().replace(' ', '-')}-{st.session_state['reporting_month']:%Y-%m}.csv",
            mime="text/csv",
            use_container_width=True,
            key="download_email_results",
        )

        _inline_dashboard_publish("email", result, st.session_state["reporting_month"], location=st.session_state["location"])

        st.markdown('<p class="section-label">Google Sheets destination</p>', unsafe_allow_html=True)
        spreadsheet_target = st.text_input(
            "Spreadsheet URL or ID",
            value=_default_spreadsheet_target(),
            key="email_spreadsheet_target",
            placeholder="https://docs.google.com/spreadsheets/d/...",
            help="The spreadsheet must be shared with your Google service-account email.",
        )
        with st.expander("Creating a new spreadsheet?", expanded=False):
            st.warning("Only do this when creating a NEW spreadsheet.")
            st.markdown(
                "Share the Google Sheet with this email and give it **Editor** access:"
            )
            st.code(GOOGLE_SERVICE_ACCOUNT_EMAIL, language=None)
            st.caption("Use the copy button above, then paste the email into Google Sheets → Share.")
        send = st.button(
            "Send to Google Sheets",
            type="primary",
            use_container_width=True,
            disabled=not spreadsheet_target.strip(),
        )
        if send:
            try:
                credentials = dict(st.secrets["google_service_account"])
                client = service_account_client(credentials)
                write_result = write_email_performance(
                    client=client,
                    spreadsheet_url_or_id=spreadsheet_target,
                    reporting_month=st.session_state["reporting_month"],
                    location=st.session_state["location"],
                    result=result,
                )
                st.success(
                    f"Updated {write_result.updated_rows} rows in "
                    f"{write_result.worksheet_title} for {write_result.month_name}."
                )
                st.link_button(
                    f"Open {write_result.worksheet_title}",
                    write_result.spreadsheet_url,
                    use_container_width=True,
                )
            except KeyError:
                st.error(
                    "Google credentials were not found. Add [google_service_account] "
                    "to .streamlit/secrets.toml and restart the app."
                )
            except ReportError as exc:
                st.error(str(exc))


def _dashboard_frame(result: MatadorDashboardResult) -> pd.DataFrame:
    rows = [*result.locations, result.totals]
    return pd.DataFrame(
        [
            {
                "Location": item.location,
                "Leads": item.leads,
                "Engaged Contacts": item.engaged_contacts,
                "Lead → Engaged": item.lead_to_engaged,
                "Total Appointments": item.total_appointments,
                "Lead → Appointment Rate": item.lead_to_appointment,
                "AI Influenced Appointments": item.ai_influenced_appointments,
                "AI Appt %": item.ai_appointment_percent,
            }
            for item in rows
        ]
    )


def _matador_dashboard_page() -> None:
    st.markdown(
        """
        <div class="matador-hero">
          <h1>Matador Dashboard</h1>
          <p>Track engagement, appointment conversion, and AI-influenced appointments by location and month.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    reporting_month = _month_year_selector("dashboard")
    if st.session_state.get("dashboard_reporting_month") not in (None, reporting_month):
        st.session_state.pop("dashboard_source", None)
        st.session_state.pop("dashboard_result", None)

    st.markdown('<p class="section-label">Upload source reports</p>', unsafe_allow_html=True)
    columns = st.columns(3)
    engage_upload = columns[0].file_uploader("AI Engage Per-Dealer", type=("csv",), key="dashboard_engage")
    follow_up_upload = columns[1].file_uploader("AI Follow-Up Per-Dealer", type=("csv",), key="dashboard_follow_up")
    reply_upload = columns[2].file_uploader("AI Reply Per-Dealer", type=("csv",), key="dashboard_reply")
    ready = all((engage_upload, follow_up_upload, reply_upload))
    load = st.button("Load Matador Reports", type="primary", use_container_width=True, disabled=not ready)
    if not ready:
        st.caption("Upload all three CSV reports to load the location totals.")
    st.caption("Safety check: all three files must use the same reporting period and match the selected month and year.")

    if load:
        try:
            with tempfile.TemporaryDirectory(prefix="matador-dashboard-") as temp_name:
                directory = Path(temp_name)
                source = MatadorDashboardProcessor().process_sources(
                    _save_upload(engage_upload, directory, "engage.csv"),
                    _save_upload(follow_up_upload, directory, "follow_up.csv"),
                    _save_upload(reply_upload, directory, "reply.csv"),
                )
            _validate_selected_period(reporting_month, source.period_start, source.period_end)
            st.session_state["dashboard_source"] = source
            st.session_state["dashboard_reporting_month"] = reporting_month
            st.session_state.pop("dashboard_result", None)
        except (ReportError, ValueError) as exc:
            st.session_state.pop("dashboard_source", None)
            st.session_state.pop("dashboard_result", None)
            st.error(str(exc))

    source = st.session_state.get("dashboard_source")
    if source is None:
        return

    st.divider()
    st.subheader(f"{st.session_state['dashboard_reporting_month']:%B %Y}")
    st.caption(
        f"Source period: {_friendly_date(source.period_start)}–{_friendly_date(source.period_end)}. "
        "AI Influenced Appointments combines AI Engage, AI Follow-Up, and AI Reply."
    )
    st.markdown('<p class="section-label">Enter total appointments</p>', unsafe_allow_html=True)
    st.caption("Enter the total appointments for each location for this reporting period.")
    appointment_totals: dict[str, int] = {}
    input_columns = st.columns(3)
    for index, location in enumerate(source.locations):
        appointment_totals[location] = int(
            input_columns[index % 3].number_input(
                location,
                min_value=0,
                step=1,
                key=f"dashboard_total_{source.period_start:%Y_%m}_{location}",
            )
        )
    generate = st.button("Generate Matador Dashboard", type="primary", use_container_width=True)
    if generate:
        st.session_state["dashboard_result"] = MatadorDashboardProcessor().build_result(source, appointment_totals)

    result = st.session_state.get("dashboard_result")
    if result is None:
        return

    st.markdown('<p class="section-label">Dashboard preview</p>', unsafe_allow_html=True)
    st.dataframe(
        _dashboard_frame(result),
        hide_index=True,
        use_container_width=True,
        column_config={
            "Leads": st.column_config.NumberColumn(format="localized"),
            "Engaged Contacts": st.column_config.NumberColumn(format="localized"),
            "Total Appointments": st.column_config.NumberColumn(format="localized"),
            "AI Influenced Appointments": st.column_config.NumberColumn(format="localized"),
            "Lead → Engaged": st.column_config.NumberColumn(format="percent"),
            "Lead → Appointment Rate": st.column_config.NumberColumn(format="percent"),
            "AI Appt %": st.column_config.NumberColumn(format="percent"),
        },
    )
    dashboard_export = _dashboard_frame(result)
    dashboard_export.insert(0, "Reporting Month", st.session_state["dashboard_reporting_month"].strftime("%B %Y"))
    st.download_button(
        "Download Results CSV",
        data=_csv_download_data(
            dashboard_export,
            ("Lead → Engaged", "Lead → Appointment Rate", "AI Appt %"),
        ),
        file_name=f"matador-dashboard-{st.session_state['dashboard_reporting_month']:%Y-%m}.csv",
        mime="text/csv",
        use_container_width=True,
        key="download_dashboard_results",
    )

    _inline_dashboard_publish("dashboard", result, st.session_state["dashboard_reporting_month"])

    st.markdown('<p class="section-label">Google Sheets destination</p>', unsafe_allow_html=True)
    same_sheet = st.checkbox(
        "Use the same spreadsheet as Email Template Performance",
        value=True,
        help="Turn this off to enter a different Google Spreadsheet.",
    )
    if same_sheet:
        default_target = st.session_state.get("email_spreadsheet_target", _default_spreadsheet_target())
        target_key = "dashboard_same_spreadsheet_target"
    else:
        default_target = ""
        target_key = "dashboard_other_spreadsheet_target"
    target = st.text_input(
        "Spreadsheet URL or ID",
        value=default_target,
        key=target_key,
        placeholder="https://docs.google.com/spreadsheets/d/...",
    )
    with st.expander("Creating a new spreadsheet?", expanded=False):
        st.warning("Only do this when creating a NEW spreadsheet.")
        st.markdown("Share the Google Sheet with this email and give it **Editor** access:")
        st.code(GOOGLE_SERVICE_ACCOUNT_EMAIL, language=None)
    send = st.button("Send Matador Dashboard to Google Sheets", type="primary", use_container_width=True, disabled=not target.strip())
    if send:
        try:
            credentials = dict(st.secrets["google_service_account"])
            client = service_account_client(credentials)
            write_result = write_matador_dashboard(
                client,
                target,
                st.session_state["dashboard_reporting_month"],
                result,
            )
            st.success(f"Updated {write_result.worksheet_title} for {write_result.month_name}.")
            st.link_button("Open Matador Dashboard", write_result.spreadsheet_url, use_container_width=True)
        except KeyError:
            st.error("Google credentials were not found. Add [google_service_account] to .streamlit/secrets.toml and restart the app.")
        except ReportError as exc:
            st.error(str(exc))


def _lead_source_frame(result: LeadSourcePerformanceResult) -> pd.DataFrame:
    rows = [{
        "Rank": item.rank, "Lead Source": item.lead_source, "Dealers": item.dealers,
        "Leads": item.leads, "Engaged Leads": item.engaged_leads,
        "Engagement Rate": item.engagement_rate, "AI Influenced Appointments": item.ai_influenced_appointments,
        "AI Influenced Appointment Rate": item.ai_influenced_appointment_rate, "User Appointments": item.user_appointments,
        "AI Appointments": item.ai_appointments, "AI Appointment Rate": item.ai_appointment_rate,
        "Team Loop-Ins": item.team_loop_ins, "Loop-In Rate": item.loop_in_rate,
    } for item in result.top_sources]
    totals = {
        "Rank": "",
        "Lead Source": "Top 15 Total",
        "Dealers": "",
        "Leads": sum(item.leads for item in result.top_sources),
        "Engaged Leads": sum(item.engaged_leads for item in result.top_sources),
        "AI Influenced Appointments": sum(item.ai_influenced_appointments for item in result.top_sources),
        "User Appointments": sum(item.user_appointments for item in result.top_sources),
        "AI Appointments": sum(item.ai_appointments for item in result.top_sources),
        "Team Loop-Ins": sum(item.team_loop_ins for item in result.top_sources),
    }
    leads = totals["Leads"]
    totals["Engagement Rate"] = totals["Engaged Leads"] / leads if leads else None
    totals["AI Influenced Appointment Rate"] = totals["AI Influenced Appointments"] / leads if leads else None
    totals["AI Appointment Rate"] = totals["AI Appointments"] / leads if leads else None
    totals["Loop-In Rate"] = totals["Team Loop-Ins"] / leads if leads else None
    rows.append(totals)
    return pd.DataFrame(rows)


def _lead_source_page() -> None:
    st.markdown('<div class="matador-hero"><h1>Lead Source Performance</h1><p>Rank the highest-volume lead sources and measure engagement and AI outcomes.</p></div>', unsafe_allow_html=True)
    reporting_month = _month_year_selector("lead_source")
    if st.session_state.get("lead_source_reporting_month") not in (None, reporting_month):
        st.session_state.pop("lead_source_result", None)
    upload_mode = st.radio(
        "How are the location reports organized?",
        ("One CSV for all locations", "Separate CSV for each location"),
        horizontal=True,
        key="lead_source_upload_mode",
    )
    uploads: dict[str, object] = {}
    if upload_mode == "One CSV for all locations":
        upload = st.file_uploader("Lead Sources Report", type=("csv",), key="lead_source_upload")
        if upload is not None:
            uploads["all_locations"] = upload
    else:
        st.caption("Upload the available location reports. Locations that are not included this month may be left blank.")
        columns = st.columns(2)
        for index, location in enumerate(LOCATIONS):
            location_upload = columns[index % 2].file_uploader(
                f"{location} Lead Sources Report",
                type=("csv",),
                key=f"lead_source_upload_{location.casefold().replace(' ', '_')}",
            )
            if location_upload is not None:
                uploads[location] = location_upload
    st.caption("The top 15 sources are selected dynamically by Leads for the uploaded month. The reporting period must match the selected month and year.")
    generate = st.button("Generate Lead Source Performance", type="primary", use_container_width=True, disabled=not uploads)
    if generate:
        try:
            with tempfile.TemporaryDirectory(prefix="lead-source-") as temp_name:
                paths = tuple(
                    _save_upload(upload, Path(temp_name), f"lead_sources_{index}.csv")
                    for index, upload in enumerate(uploads.values())
                )
                processor = LeadSourcePerformanceProcessor()
                result = (
                    processor.process(paths[0])
                    if upload_mode == "One CSV for all locations"
                    else processor.process_many(paths)
                )
            _validate_selected_period(reporting_month, result.period_start, result.period_end)
            st.session_state["lead_source_result"] = result
            st.session_state["lead_source_reporting_month"] = reporting_month
        except (ReportError, ValueError) as exc:
            st.session_state.pop("lead_source_result", None)
            st.error(str(exc))
    result = st.session_state.get("lead_source_result")
    if result is None:
        return
    st.divider()
    a, b, c = st.columns(3)
    a.metric("Lead Sources Detected", f"{result.all_source_count:,}")
    b.metric("All Leads", f"{result.all_leads:,}")
    c.metric("Sources Included", f"{len(result.top_sources):,}")
    st.dataframe(
        _lead_source_frame(result), hide_index=True, use_container_width=True,
        column_config={name: st.column_config.NumberColumn(format="percent") for name in ("Engagement Rate", "AI Influenced Appointment Rate", "AI Appointment Rate", "Loop-In Rate")},
    )
    lead_source_export = _lead_source_frame(result)
    lead_source_export.insert(0, "Reporting Month", st.session_state["lead_source_reporting_month"].strftime("%B %Y"))
    st.download_button(
        "Download Results CSV",
        data=_csv_download_data(
            lead_source_export,
            ("Engagement Rate", "AI Influenced Appointment Rate", "AI Appointment Rate", "Loop-In Rate"),
        ),
        file_name=f"lead-source-performance-{st.session_state['lead_source_reporting_month']:%Y-%m}.csv",
        mime="text/csv",
        use_container_width=True,
        key="download_lead_source_results",
    )
    _inline_dashboard_publish("leadSources", result, st.session_state["lead_source_reporting_month"])

    st.markdown('<p class="section-label">Google Sheets destination</p>', unsafe_allow_html=True)
    same_sheet = st.checkbox("Use the same spreadsheet as the other reports", value=True, key="lead_source_same_sheet")
    default_target = st.session_state.get("email_spreadsheet_target", _default_spreadsheet_target()) if same_sheet else ""
    target = st.text_input("Spreadsheet URL or ID", value=default_target, key="lead_source_same_target" if same_sheet else "lead_source_other_target")
    with st.expander("Creating a new spreadsheet?", expanded=False):
        st.warning("Only do this when creating a NEW spreadsheet.")
        st.markdown("Share the Google Sheet with this email and give it **Editor** access:")
        st.code(GOOGLE_SERVICE_ACCOUNT_EMAIL, language=None)
        st.caption("Use the copy button above, then paste the email into Google Sheets → Share.")
    send = st.button("Send Lead Source Performance to Google Sheets", type="primary", use_container_width=True, disabled=not target.strip())
    if send:
        try:
            client = service_account_client(dict(st.secrets["google_service_account"]))
            write_result = write_lead_source_performance(client, target, st.session_state["lead_source_reporting_month"], result)
            st.success(f"Updated {write_result.worksheet_title} for {write_result.month_name}.")
            st.link_button("Open Lead Source Performance", write_result.spreadsheet_url, use_container_width=True)
        except KeyError:
            st.error("Google credentials were not found. Add [google_service_account] to .streamlit/secrets.toml and restart the app.")
        except ReportError as exc:
            st.error(str(exc))


def _volie_service_frame(result: VolieSmsServiceAppointmentsResult) -> pd.DataFrame:
    rows = [
        {
            "Location": item.location,
            "Bitly Clicks": item.bitly_clicks,
            "Active Users": item.active_users,
            "GA4 Active Users ÷ Bitly Clicks": item.appointment_rate,
            "Matched Event": (
                item.event_name
                or ("Not found — counted as 0" if item.ga4_report_uploaded else "GA4 report not uploaded")
            ),
        }
        for item in result.locations
    ]
    rows.append(
        {
            "Location": "Comparable Total" if result.total_bitly_clicks else "Total",
            "Bitly Clicks": result.comparable_bitly_clicks if result.total_bitly_clicks else None,
            "Active Users": result.comparable_active_users if result.total_bitly_clicks else result.total_active_users,
            "GA4 Active Users ÷ Bitly Clicks": result.overall_appointment_rate,
            "Matched Event": "",
        }
    )
    return pd.DataFrame(rows)


def _volie_sms_service_page() -> None:
    st.markdown(
        '<div class="matador-hero"><h1>Volie SMS Service Appointments</h1>'
        '<p>Track GA4 active users who submitted a service appointment after a Volie SMS visit.</p></div>',
        unsafe_allow_html=True,
    )
    reporting_month = _month_year_selector("volie_service")
    if st.session_state.get("volie_service_reporting_month") not in (None, reporting_month):
        st.session_state.pop("volie_service_result", None)

    st.markdown('<p class="section-label">Upload GA4 service reports</p>', unsafe_allow_html=True)
    st.caption(
        "Upload the available location reports. The app accepts both "
        "form_submission_service_appt and asc_form_submission_service_appt."
    )
    uploads: dict[str, object] = {}
    columns = st.columns(2)
    for index, location in enumerate(LOCATIONS):
        upload = columns[index % 2].file_uploader(
            f"{location} GA4 Service Report",
            type=("csv",),
            key=f"volie_service_upload_{location.casefold().replace(' ', '_')}",
        )
        if upload is not None:
            uploads[location] = upload

    st.markdown('<p class="section-label">Upload Bitly report</p>', unsafe_allow_html=True)
    bitly_upload = st.file_uploader(
        "Bitly Links by Clicks Report",
        type=("csv",),
        key="volie_service_bitly_upload",
    )
    st.caption(
        "Optional: adds Schedule Service clicks and calculates GA4 active users ÷ Bitly clicks for each location. "
        "The Bitly filename and reporting period are not validated."
    )

    generate = st.button(
        "Generate Volie SMS Service Appointments",
        type="primary",
        use_container_width=True,
        disabled=not uploads,
    )
    if generate:
        try:
            with tempfile.TemporaryDirectory(prefix="volie-service-") as temp_name:
                paths = {
                    location: _save_upload(upload, Path(temp_name), f"{index}.csv")
                    for index, (location, upload) in enumerate(uploads.items())
                }
                bitly_path = (
                    _save_upload(bitly_upload, Path(temp_name), bitly_upload.name)
                    if bitly_upload is not None else None
                )
                result = VolieSmsServiceAppointmentsProcessor().process(paths, bitly_path)
            _validate_selected_period(reporting_month, result.period_start, result.period_end)
            st.session_state["volie_service_result"] = result
            st.session_state["volie_service_reporting_month"] = reporting_month
        except (ReportError, ValueError) as exc:
            st.session_state.pop("volie_service_result", None)
            st.error(str(exc))

    result = st.session_state.get("volie_service_result")
    if result is None:
        return

    st.divider()
    a, b, c, d = st.columns(4)
    a.metric("Total Active Users", f"{result.total_active_users:,}")
    b.metric("Schedule Service Clicks", f"{result.total_bitly_clicks:,}" if result.total_bitly_clicks else "—")
    c.metric("GA4 Active Users ÷ Bitly Clicks", _percent(result.overall_appointment_rate))
    d.metric("Reporting Through", _friendly_date(result.period_end))
    missing_events = [
        item.location for item in result.locations
        if item.ga4_report_uploaded and not item.event_found
    ]
    if missing_events:
        st.warning(
            "No service-appointment event row was found for "
            + ", ".join(missing_events)
            + ". Those locations are shown as 0."
        )
    missing_ga4 = [
        item.location for item in result.locations if not item.ga4_report_uploaded
    ]
    if missing_ga4:
        st.info(
            "Bitly clicks were found, but no GA4 report was uploaded for "
            + ", ".join(missing_ga4)
            + ". These locations are excluded from the comparable conversion rate."
        )
    frame = _volie_service_frame(result)
    st.dataframe(
        frame,
        hide_index=True,
        use_container_width=True,
        column_config={
            "GA4 Active Users ÷ Bitly Clicks": st.column_config.NumberColumn(format="percent")
        },
    )
    export = frame.copy()
    export.insert(0, "Reporting Start", result.period_start.isoformat())
    export.insert(1, "Reporting End", result.period_end.isoformat())
    st.download_button(
        "Download Results CSV",
        data=_csv_download_data(export, ("GA4 Active Users ÷ Bitly Clicks",)),
        file_name=f"volie-sms-service-appointments-{reporting_month:%Y-%m}.csv",
        mime="text/csv",
        use_container_width=True,
        key="download_volie_service_results",
    )

    _inline_dashboard_publish("volie", result, st.session_state["volie_service_reporting_month"])

    st.markdown('<p class="section-label">Google Sheets destination</p>', unsafe_allow_html=True)
    same_sheet = st.checkbox(
        "Use the same spreadsheet as the other reports",
        value=True,
        key="volie_service_same_sheet",
    )
    default_target = (
        st.session_state.get("email_spreadsheet_target", _default_spreadsheet_target())
        if same_sheet else ""
    )
    target = st.text_input(
        "Spreadsheet URL or ID",
        value=default_target,
        key="volie_service_same_target" if same_sheet else "volie_service_other_target",
    )
    with st.expander("Creating a new spreadsheet?", expanded=False):
        st.warning("Only do this when creating a NEW spreadsheet.")
        st.markdown("Share the Google Sheet with this email and give it **Editor** access:")
        st.code(GOOGLE_SERVICE_ACCOUNT_EMAIL, language=None)
        st.caption("Use the copy button above, then paste the email into Google Sheets → Share.")
    send = st.button(
        "Send Volie SMS Service Appointments to Google Sheets",
        type="primary",
        use_container_width=True,
        disabled=not target.strip(),
    )
    if send:
        try:
            client = service_account_client(dict(st.secrets["google_service_account"]))
            write_result = write_volie_sms_service_appointments(
                client,
                target,
                st.session_state["volie_service_reporting_month"],
                result,
            )
            st.success(f"Updated {write_result.worksheet_title} for {write_result.month_name}.")
            st.link_button("Open Volie SMS Service Appointments", write_result.spreadsheet_url, use_container_width=True)
        except KeyError:
            st.error("Google credentials were not found. Add [google_service_account] to .streamlit/secrets.toml and restart the app.")
        except ReportError as exc:
            st.error(str(exc))



def _inline_dashboard_publish(
    category: str,
    result: EmailPerformanceResult | MatadorDashboardResult | LeadSourcePerformanceResult | VolieSmsServiceAppointmentsResult,
    reporting_month: date,
    *,
    location: str | None = None,
) -> None:
    """Publish exactly this report from its preview, without changing other reports."""
    names = {
        "email": "Email Template Performance",
        "dashboard": "Matador Dashboard",
        "leadSources": "Lead Source Performance",
        "volie": "Volie SMS Service Appointments",
    }
    try:
        rows = serialize_report(category, result, location=location)
    except PublishError as exc:
        st.error(f"Cannot prepare dashboard data: {exc}")
        return

    st.markdown('<p class="section-label">Publish to Quarterly Dashboard</p>', unsafe_allow_html=True)
    st.caption(
        f"Add or update {names[category]} for {reporting_month:%B %Y}"
        + (f" — {location}" if location else "")
        + f" · {len(rows)} rows. Only this report's dashboard data will be replaced."
    )
    with st.expander("Review dashboard data before publishing", expanded=False):
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        if category == "email":
            st.caption("Only this dealership's email records are replaced. Other locations and CTA totals are preserved.")
        else:
            st.caption("Only this month and report category are replaced. Other months and report categories are preserved.")

    try:
        settings = st.secrets.get("github", {})
        token = str(settings.get("token", ""))
        owner = str(settings.get("owner", "bdcserpentini"))
        repository = str(settings.get("repository", "serpentini-reports"))
        branch = str(settings.get("branch", "main"))
    except Exception:
        token = ""
        owner, repository, branch = "bdcserpentini", "serpentini-reports", "main"

    if not token:
        st.error("GitHub publishing is not configured. Add [github] credentials in Streamlit Secrets; never commit the token to GitHub.")
        return

    st.caption(f"Destination: {owner}/{repository} · {branch} · reports.json")
    st.warning("The quarterly dashboard is publicly accessible. Publish only approved metrics.")
    # A change in source report, selected month or location requires fresh approval.
    fingerprint = hashlib.sha256(json.dumps({
        "category": category,
        "month": reporting_month_key(reporting_month),
        "location": location,
        "rows": rows,
    }, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    confirmed = st.checkbox(
        "I reviewed this report and approve publishing it to the public dashboard",
        key=f"approve_{category}_{fingerprint}",
    )
    if st.button(
        "Add / Update Quarterly Dashboard",
        type="primary",
        disabled=not confirmed,
        use_container_width=True,
        key=f"publish_{category}_{fingerprint}",
    ):
        try:
            message = publish_report(
                token, owner, repository, branch,
                reporting_month_key(reporting_month), category, rows, location=location,
            )
            st.success(message)
            st.caption("If the live dashboard still shows old numbers, refresh it with Ctrl + Shift + R.")
        except PublishError as exc:
            st.error(str(exc))


def main() -> None:
    _configure_page()
    page = st.sidebar.radio(
        "Report Page",
        (
            "Email Template Performance",
            "Matador Dashboard",
            "Lead Source Performance",
            "Volie SMS Service Appointments",
            "BDC Agent Performance",
            "Manage BDC Agents",
        ),
    )
    if page == "Email Template Performance":
        _email_template_page()
    elif page == "Matador Dashboard":
        _matador_dashboard_page()
    elif page == "Lead Source Performance":
        _lead_source_page()
    elif page == "Volie SMS Service Appointments":
        _volie_sms_service_page()
    elif page == "BDC Agent Performance":
        _bdc_report_page()
    else:
        _bdc_manage_page()


if __name__ == "__main__":
    main()
