"""Streamlit BDC roster management and user-performance report preview."""
from __future__ import annotations
import hashlib
import json
import uuid
from datetime import date
import calendar
import pandas as pd
import streamlit as st
from matador_reporting.github_publisher import PublishError, publish_report, serialize_report
from .processor import BdcReportError, process_csv, validate_roster
from .roster_store import load_seed, fetch_roster, save_roster


def _settings() -> dict:
    # Explicitly separate write permission for the Streamlit APP repo from dashboard publishing.
    try: settings=st.secrets.get('bdc_roster_github', {})
    except Exception: settings={}
    return {'token':str(settings.get('token','')),'owner':str(settings.get('owner','BDCSerpentini')),
            'repository':str(settings.get('repository','Report-Website-Updater')),
            'branch':str(settings.get('branch','main'))}


def _ensure_loaded() -> None:
    if 'bdc_roster_draft' in st.session_state:return
    settings=_settings()
    roster=load_seed()
    sha=None
    message='Using the roster bundled with this application.'
    if settings['token']:
        try:
            roster,sha=fetch_roster(settings['token'], settings['owner'], settings['repository'], settings['branch'])
            message='Loaded approved roster from GitHub.'
        except PublishError as exc:
            message=f'Could not load live roster; using bundled copy. Remote saving is disabled until this is fixed: {exc}'
    st.session_state['bdc_roster_draft']=roster
    st.session_state['bdc_roster_sha']=sha
    st.session_state['bdc_roster_source_message']=message


def _editor_frame(roster: dict) -> pd.DataFrame:
    return pd.DataFrame([{'ID':a['id'],'Display Name':a['display_name'],
          'Exact Matador Names':'; '.join(a['matador_names']),
          'Start Date':a.get('start_date') or '', 'End Date':a.get('end_date') or '',
          'Home Location':a.get('home_location') or '',
          'Status':('Inactive' if a.get('end_date') and date.fromisoformat(a['end_date']) < date.today() else 'Active')} for a in roster['agents']])


def _from_editor(frame: pd.DataFrame) -> dict:
    agents=[]
    for r in frame.fillna('').to_dict('records'):
        aliases=[x.strip() for x in str(r['Exact Matador Names']).split(';') if x.strip()]
        agents.append({'id':str(r['ID']), 'display_name':str(r['Display Name']).strip(),
           'matador_names':aliases, 'start_date':str(r['Start Date']).strip() or None,
           'end_date':str(r['End Date']).strip() or None,
           'home_location':str(r['Home Location']).strip()})
    doc={'schema_version':1,'agents':agents}
    validate_roster(doc)
    return doc


def manage_page() -> None:
    st.title('Manage BDC Agents')
    st.caption('An approved name roster filters the entire Matador Users export. CRM roles are not used. Former agents remain in history.')
    _ensure_loaded()
    st.info(st.session_state['bdc_roster_source_message'])
    st.markdown('**Agent roster** · Leave Start/End Date blank when unknown. End Date is inclusive. Use semicolons between approved Matador names.')
    original=st.session_state['bdc_roster_draft']
    frame=st.data_editor(_editor_frame(original), use_container_width=True, hide_index=True,
         disabled=['ID','Status'], num_rows='fixed', key='bdc_roster_editor')
    if st.button('Apply roster edits to preview', key='apply_roster_edit'):
        try:
            st.session_state['bdc_roster_draft']=_from_editor(frame)
            st.success('Draft updated. Save to GitHub below for durable changes.')
        except (ValueError, BdcReportError) as exc:st.error(str(exc))
    with st.form('bdc_add_agent',clear_on_submit=True):
        st.subheader('Add an approved BDC agent')
        c1,c2=st.columns(2)
        name=c1.text_input('Dashboard display name')
        csv_name=c2.text_input('Exact name from Matador CSV')
        home=st.selectbox('Home dealership (optional metadata)', ['','Medina','Orrville','Strongsville','Tallmadge','Westlake','Willoughby Hills','CDJR'])
        if st.form_submit_button('Add agent to roster'):
            if not name.strip() or not csv_name.strip():st.error('Both names are required.')
            else:
                draft=json.loads(json.dumps(st.session_state['bdc_roster_draft']))
                draft['agents'].append({'id':'bdc_'+uuid.uuid4().hex[:12], 'display_name':name.strip(),
                    'matador_names':[csv_name.strip()], 'start_date':None,'end_date':None,'home_location':home})
                try:
                    validate_roster(draft)
                    st.session_state['bdc_roster_draft']=draft
                    st.success('Agent added to draft. Save the roster to persist the addition.')
                    st.rerun()
                except (ValueError, BdcReportError) as exc:st.error(str(exc))
    st.divider()
    st.subheader('Save approved roster')
    settings=_settings()
    approved=st.session_state['bdc_roster_draft']
    raw=(json.dumps(approved,indent=2,ensure_ascii=False)+'\n').encode('utf-8')
    st.download_button('Download roster JSON (backup / manual update)',raw,'bdc_agents.json','application/json')
    if settings['token'] and st.session_state['bdc_roster_sha']:
        st.caption(f"Save destination: {settings['owner']}/{settings['repository']} · {settings['branch']} · bdc_agents.json")
        if st.button('Save roster to GitHub', type='primary'):
            try:
                save_roster(approved,settings['token'],settings['owner'],settings['repository'],settings['branch'],st.session_state['bdc_roster_sha'])
                # re-fetch, don't assume commit SHA is the content SHA
                remote, sha=fetch_roster(settings['token'], settings['owner'], settings['repository'], settings['branch'])
                st.session_state['bdc_roster_draft']=remote
                st.session_state['bdc_roster_sha']=sha
                st.success('Approved roster saved to GitHub. Historical report snapshots are unchanged.')
            except (PublishError,BdcReportError) as exc:st.error(str(exc))
    else:
        st.warning('GitHub roster saving is not configured. Changes are only temporary in this session. Download the JSON and commit it as bdc_agents.json to the Streamlit repository, or configure [bdc_roster_github] Secrets for one-click saving.')


def report_page() -> None:
    st.title('BDC Agent Performance')
    st.caption('Approved BDC users only · Matador Users — All Users CSV · One reporting month per upload')
    _ensure_loaded()
    roster=st.session_state['bdc_roster_draft']
    st.info(f"Approved roster: {len(roster['agents'])} agents. Matador user roles are ignored.")
    upload=st.file_uploader('Upload Matador Users – All Users CSV',type=['csv'],key='bdc_csv')
    if upload is None:return
    uploaded_bytes = upload.getvalue()
    try:
        detected = process_csv(uploaded_bytes, roster)
    except BdcReportError as exc:
        st.error(str(exc))
        return

    # A file-specific key resets the month selection whenever a different CSV is uploaded.
    # Always propose the reporting month found in the export rather than today's month.
    csv_fingerprint = hashlib.sha256(uploaded_bytes).hexdigest()[:16]
    detected_month = detected['month']
    detected_year = int(detected_month[:4])
    years = list(range(min(2025, detected_year), max(date.today().year + 1, detected_year) + 1))
    month_options = [f'{year}-{month:02d}' for year in years for month in range(1, 13)]
    selected_month = st.selectbox(
        'Reporting month',
        options=month_options,
        index=month_options.index(detected_month),
        format_func=lambda value: f'{calendar.month_name[int(value[5:7])]} {value[:4]}',
        key=f'bdc_reporting_month_{csv_fingerprint}',
        help='Select the month this report should update. It must agree with the CSV reporting period.',
    )
    st.caption(f"CSV reporting period: {detected['period_start']} through {detected['period_end']}")
    if selected_month != detected_month:
        st.error(
            f'Wrong reporting month: you selected {calendar.month_name[int(selected_month[5:7])]} '
            f'{selected_month[:4]}, but the uploaded CSV is for '
            f'{calendar.month_name[int(detected_month[5:7])]} {detected_month[:4]}. '
            'Choose the CSV month or upload the matching export. Nothing can be published until they match.'
        )
        return
    # The selected month is explicitly validated again by the processor.
    try:
        res = process_csv(uploaded_bytes, roster, expected_month=selected_month)
    except BdcReportError as exc:
        st.error(str(exc))
        return
    st.info(f"Selected report: {calendar.month_name[int(selected_month[5:7])]} {selected_month[:4]} · Publishing updates only this month.")
    c1,c2,c3=st.columns(3)
    c1.metric('Matched BDC agents',res['matched_agents'])
    c2.metric('Non-roster users excluded',res['excluded_users'])
    c3.metric('Approved agents missing',len(res['missing_agents']))
    if res['outside_employment']:
        st.warning(f"Excluded {len(res['outside_employment'])} matched rows outside their configured employment dates.")
    with st.expander('Review exclusions and missing approved agents'):
        st.write('Missing approved agents:', ', '.join(res['missing_agents']) or 'None')
        st.write('Non-roster users:', ', '.join(res['excluded_user_names']) or 'None')
        if res['outside_employment']:st.dataframe(pd.DataFrame(res['outside_employment']),hide_index=True)
    if not res['agents']:
        st.warning('No approved BDC agents matched this file. Nothing to export.')
        return
    df=pd.DataFrame([{'Agent':a['name'],'Messages Sent':a['messages'], 'Customers Messaged':a['customers'],
         'Handoffs':a['handoffs'], 'Handoff Reply Rate':None if a['handoffReplyRate'] is None else f"{a['handoffReplyRate']:.1%}",
         'Most Messaged Location':a['mostMessagedLocation'] or 'No messages',
         'Rate Estimated':a['replyRateEstimated']} for a in res['agents']])
    st.subheader('Agent performance preview')
    st.dataframe(df,hide_index=True,use_container_width=True)
    st.caption('Multiple location entries are summed. Reply rates across multiple entries are estimated by handoff weighting; the source provides rounded rates, not reply counts.')
    with st.expander('Agent totals and location breakdown'):
        for a in res['agents']:
            if len(a['locations'])>1:
                st.markdown(f"**{a['name']}**")
                st.dataframe(pd.DataFrame(a['locations']),hide_index=True,use_container_width=True)
    st.download_button('Download agent metrics CSV',df.to_csv(index=False).encode('utf-8-sig'),f'BDC_Agents_{res["month"]}.csv','text/csv')
    st.download_button('Download BDC report JSON',json.dumps({'month':res['month'],'bdcAgents':res['agents']},indent=2).encode(),f'BDC_Agents_{res["month"]}.json','application/json')
    st.divider()
    st.subheader('Publish to Quarterly Dashboard')
    st.caption(f"Add or update BDC agent performance for {res['month']}. Existing reporting categories, other months and the approved roster remain unchanged.")
    rows = serialize_report('bdcAgents', res)
    with st.expander('Review published agent records'):
        st.dataframe(df, hide_index=True, use_container_width=True)
        st.caption('The destination is reports.json. This includes named employee performance and is publicly visible on GitHub Pages.')
    try:
        settings = st.secrets.get('github', {})
        token = str(settings.get('token',''))
        owner = str(settings.get('owner','bdcserpentini'))
        repository = str(settings.get('repository','serpentini-reports'))
        branch = str(settings.get('branch','main'))
    except Exception:
        token=''
        owner,repository,branch='bdcserpentini','serpentini-reports','main'
    if not token:
        st.error('Dashboard publishing requires [github] credentials in Streamlit Secrets.')
        return
    st.caption(f'Destination: {owner}/{repository} · {branch} · reports.json')
    st.warning('This is a PUBLIC dashboard. Confirm internal authorization to disclose named agent performance before publishing.')
    fingerprint = hashlib.sha256(json.dumps({'month':res['month'],'rows':rows},sort_keys=True).encode()).hexdigest()[:16]
    approved = st.checkbox('I reviewed this report and am authorized to publish named agent performance publicly',key=f'bdc_publish_approve_{fingerprint}')
    if st.button('Add / Update Quarterly Dashboard',type='primary',disabled=not approved,
                 use_container_width=True,key=f'bdc_publish_{fingerprint}'):
        try:
            message=publish_report(token,owner,repository,branch,res['month'],'bdcAgents',rows)
            st.success(message)
            st.caption('Refresh the dashboard with Ctrl + Shift + R if the updated month does not appear immediately.')
        except PublishError as exc:
            st.error(str(exc))
    st.caption('The GitHub Pages dashboard is public. Do not publish named employee performance without internal approval.')
