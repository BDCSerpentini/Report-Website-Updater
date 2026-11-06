"""Streamlit BDC roster management and user-performance report preview."""
from __future__ import annotations
import hashlib
import json
import uuid
from datetime import date
import pandas as pd
import streamlit as st
from matador_reporting.github_publisher import PublishError
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
    digest=hashlib.sha256(upload.getvalue() + json.dumps(roster,sort_keys=True).encode()).hexdigest()
    try:res=process_csv(upload.getvalue(),roster)
    except BdcReportError as exc:
        st.error(str(exc));return
    st.caption(f"Detected reporting period: {res['period_start']} through {res['period_end']} · {res['month']}")
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
    st.warning('Dashboard publishing is not enabled for BDC agents in this first phase. The existing GitHub Pages BDC tab uses a separate July snapshot; it must be updated to read monthly bdcAgents data before automated publication is safe.')
    st.caption('The GitHub Pages dashboard is public. Do not publish named employee performance without internal approval.')
