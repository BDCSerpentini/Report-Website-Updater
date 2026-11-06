from datetime import date
from pathlib import Path
import pytest
from matador_reporting.reports.outreach import parse_outreach_csv, OutreachError
from matador_reporting.github_publisher import merge_report,serialize_report

AUTO = ('Start Date,End Date,Dealer,Customers Messaged,Customers Engaged,Reply Rate,AI Influenced Appts,Best Automation\n'
        '10/1/2026,10/31/2026,Serpentini Chevrolet of Westlake,594,255,43%,66,Price Drop\n').encode()
BC = ('Start Date,End Date,Dealer,Total Broadcasts,Customers Messaged,Reply Rate,Appts Influenced,Top Broadcasts\n'
      '10/1/2026,10/31/2026,Serpentini Chevrolet of Orrville,—,0,—,0,—\n').encode()

def test_automation_import_and_safe_merge():
    rows=parse_outreach_csv(AUTO,'automations',date(2026,10,1))
    assert rows[0]['location']=='Westlake'
    assert rows[0]['replyRate']==0.43
    assert rows[0]['engaged']==255
    initial={'schema_version':1,'months':{'2026-10':{'dashboard':[{'leads':99}],'broadcasts':[{'location':'Westlake'}]}}}
    output=merge_report(initial,'2026-10','automations',serialize_report('automations',rows))
    assert output['months']['2026-10']['automations']==rows
    assert output['months']['2026-10']['broadcasts']==initial['months']['2026-10']['broadcasts']
    assert initial['months']['2026-10']['dashboard']==output['months']['2026-10']['dashboard']

def test_broadcast_missing_count_stays_null():
    rows=parse_outreach_csv(BC,'broadcasts',date(2026,10,1))
    assert rows[0]['broadcasts'] is None
    assert rows[0]['messaged']==0
    assert rows[0]['replyRate'] is None

def test_wrong_month_rejected():
    with pytest.raises(OutreachError,match='complete selected month'):
        parse_outreach_csv(AUTO,'automations',date(2026,9,1))

def test_duplicate_rejected():
    lines=AUTO.decode().splitlines()
    with pytest.raises(OutreachError,match='Duplicate dealership'):
        parse_outreach_csv(('\n'.join([*lines,lines[1]])+'\n').encode(),'automations',date(2026,10,1))
