from copy import deepcopy
from matador_reporting.github_publisher import serialize_report, merge_report, PublishError
from matador_reporting.reports.bdc_agents.processor import process_csv
from matador_reporting.reports.bdc_agents.roster_store import load_seed
from pathlib import Path
import pytest


def test_publish_bdc_preserves_existing_reports_and_months():
    roster=load_seed()
    # Minimal real CSV-style fixture for Noah, excludes unrelated users
    csv=b'Start Date,End Date,User,Dealer,Messages Sent,Customers Messaged,Handoffs,Handoff Reply Rate\n2026-07-01,2026-07-31,Noah Greene,Willoughby Hills,596,325,244,9%\n2026-07-01,2026-07-31,Sales Employee,Medina,450,200,90,10%\n'
    result=process_csv(csv,roster)
    rows=serialize_report('bdcAgents',result)
    assert len(rows)==1 and rows[0]['name']=='Noah'
    before={'schema_version':1,'months':{'2026-07':{'dashboard':[{'location':'Medina','leads':1}],'email':[{'sent':5}]},'2026-08':{'volie':[{'clicks':4}]}}}
    old=deepcopy(before)
    after=merge_report(before,'2026-07','bdcAgents',rows)
    assert after['months']['2026-07']['bdcAgents']==rows
    assert after['months']['2026-07']['email']==before['months']['2026-07']['email']
    assert after['months']['2026-08']==before['months']['2026-08']
    assert before==old
    assert merge_report(after,'2026-07','bdcAgents',rows)==after

def test_invalid_bdc_rate_rejected():
    before={'schema_version':1,'months':{}}
    with pytest.raises(PublishError):
        merge_report(before,'2026-09','bdcAgents',[{'id':'bdc_001','name':'Noah','messages':1,'customers':1,'handoffs':1,'handoffReplyRate':50,'locations':[],'replyRateEstimated':False}])
