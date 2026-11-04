from datetime import date
from types import SimpleNamespace as O
import pytest
from matador_reporting.github_publisher import merge_report,serialize_report,PublishError,reporting_month_key

def test_preserves_other_categories_and_months():
    original={'schema_version':1,'months':{'2026-10':{'dashboard':[{'location':'Medina'}], 'email':[{'location':'CDJR','sent':3},{'location':'Orrville','sent':4}], 'volie':[{'users':5}]},'2026-09':{'email':[{'sent':9}]}}}
    changed=merge_report(original,'2026-10','email',[{'location':'CDJR','sent':8}],location='CDJR')
    assert changed['months']['2026-10']['email']==[{'location':'Orrville','sent':4},{'location':'CDJR','sent':8}]
    assert changed['months']['2026-10']['volie']==[{'users':5}]
    assert changed['months']['2026-09']==original['months']['2026-09']
    assert original['months']['2026-10']['email'][0]['sent']==3

def test_reject_wrong_email_location():
    with pytest.raises(PublishError):
        merge_report({'schema_version':1,'months':{}},'2026-10','email',[{'location':'Medina'}],location='CDJR')

def test_period_and_dashboard_serialization():
    x=O(locations=[O(location='Medina',leads=20,engaged_contacts=10,total_appointments=6,ai_influenced_appointments=4)])
    assert reporting_month_key(date(2026,10,1))=='2026-10'
    assert serialize_report('dashboard',x)==[{'location':'Medina','leads':20,'engaged':10,'appointments':6,'influenced':4}]

def test_email_summary_and_campaign_rows():
    x=O(campaigns=[O(reporting_group='Day 1',emails_sent=10,emails_opened=5,cta_users=2)],location_metrics=O(emails_sent=10,emails_opened=5,unique_cta_users=2))
    rows=serialize_report('email',x,location='CDJR')
    assert rows[-1]=={'location':'CDJR','campaign':'Location Total','sent':10,'opens':5,'cta':2}
