from pathlib import Path
import json
import pytest
from matador_reporting.reports.bdc_agents.processor import process_csv,validate_roster,BdcReportError
from matador_reporting.reports.bdc_agents.roster_store import load_seed

CSV_DATA = ("Start Date,End Date,User,Dealer,Messages Sent,Customers Messaged,Handoffs,Handoff Reply Rate\n"
            "2026-07-01,2026-07-31,Ang Stitt,Serpentini Chevrolet of Westlake,2191,914,456,23%\n"
            "2026-07-01,2026-07-31,Noah Greene,Serpentini Chevrolet of Willoughby Hills,596,325,244,9%\n"
            "2026-07-01,2026-07-31,Tina Funk,Serpentini Chevrolet of Strongsville,2294,1119,549,26%\n"
            "2026-07-01,2026-07-31,Jonathan Jamhour,Serpentini Chevrolet of Westlake,0,0,2,0%\n"
            "2026-07-01,2026-07-31,Phillip Blough,Serpentini Chevrolet of Strongsville,1332,610,392,24%\n").encode()


def test_seed_roster():
    r=load_seed()
    assert len(r['agents'])==21
    assert next(a for a in r['agents'] if a['display_name']=='Noah')['matador_names']==['Noah Greene']

def test_july_export_matches_approved_agents_only():
    result=process_csv(CSV_DATA,load_seed(),expected_month='2026-07')
    assert result['matched_agents']==4
    by_name={a['name']:a for a in result['agents']}
    assert by_name['Ang']['messages']==2191
    assert by_name['Noah']['messages']==596
    assert by_name['Noah']['mostMessagedLocation']=='Willoughby Hills'
    assert by_name['Jonathan']['mostMessagedLocation'] is None
    assert by_name['Tina']['handoffReplyRate']==pytest.approx(.26)
    assert 'Phillip Blough' in result['excluded_user_names']

def test_employment_dates_preserve_july_exclude_aug():
    r=load_seed()
    ang=next(a for a in r['agents'] if a['display_name']=='Ang')
    ang['end_date']='2026-07-15'
    assert any(a['name']=='Ang' for a in process_csv(CSV_DATA,r)['agents'])
    ang['end_date']='2026-06-30'
    result=process_csv(CSV_DATA,r)
    assert not any(a['name']=='Ang' for a in result['agents'])
    assert any(x['name']=='Ang Stitt' for x in result['outside_employment'])

def test_collision_prevents_incorrect_assignment():
    r=load_seed()
    r['agents'][0]['matador_names'].append('Noah Greene')
    with pytest.raises(BdcReportError,match='Duplicate Matador name'):validate_roster(r)

def test_multi_location_most_messages_and_weighted_rate():
    r=load_seed(); a=r['agents'][0]
    raw=('Start Date,End Date,User,Dealer,Messages Sent,Customers Messaged,Handoffs,Handoff Reply Rate\n'
         f'2026-07-01,2026-07-31,{a["matador_names"][0]},Serpentini Chevrolet of Medina,20,13,10,20%\n'
         f'2026-07-01,2026-07-31,{a["matador_names"][0]},Serpentini Chevrolet of Westlake,40,22,30,40%\n').encode()
    result=process_csv(raw,r)['agents'][0]
    assert result['messages']==60
    assert result['mostMessagedLocation']=='Westlake'
    assert result['replyRateEstimated']
    assert result['handoffReplyRate']==pytest.approx(.35)

def test_mixed_dates_rejected():
    raw=('Start Date,End Date,User,Dealer,Messages Sent,Customers Messaged,Handoffs,Handoff Reply Rate\n'
         '2026-07-01,2026-07-31,Noah Greene,Serpentini Chevrolet of Westlake,1,1,1,10%\n'
         '2026-08-01,2026-08-31,Noah Greene,Serpentini Chevrolet of Westlake,1,1,1,10%\n').encode()
    with pytest.raises(BdcReportError,match='mixed reporting periods'):process_csv(raw,load_seed())
