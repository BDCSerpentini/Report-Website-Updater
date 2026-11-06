"""Matador Users CSV processing: exact approved roster names, never CRM roles."""
from __future__ import annotations
import csv
import io
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

REQUIRED = {"Start Date", "End Date", "User", "Dealer", "Messages Sent", "Customers Messaged", "Handoffs", "Handoff Reply Rate"}
LOCATIONS = ("Medina", "Orrville", "Strongsville", "Tallmadge", "Westlake", "Willoughby Hills", "CDJR")

class BdcReportError(ValueError):
    pass

def normalize_name(value: str) -> str:
    return " ".join(str(value).casefold().split())

def validate_roster(roster: dict) -> None:
    if not isinstance(roster, dict) or roster.get("schema_version") != 1 or not isinstance(roster.get("agents"), list):
        raise BdcReportError("Roster must contain schema_version 1 and an agents list")
    ids, aliases = set(), {}
    for a in roster["agents"]:
        if not isinstance(a, dict) or not a.get("id") or not str(a.get("display_name", "")).strip():
            raise BdcReportError("Each agent requires a stable ID and display name")
        if a["id"] in ids:
            raise BdcReportError(f"Duplicate agent ID: {a['id']}")
        ids.add(a["id"])
        if not a.get("matador_names") or not isinstance(a["matador_names"], list):
            raise BdcReportError(f"{a['display_name']}: at least one exact Matador name is required")
        for alias in a["matador_names"]:
            key=normalize_name(alias)
            if not key:raise BdcReportError("Empty Matador name is not allowed")
            if key in aliases:raise BdcReportError(f"Duplicate Matador name '{alias}' assigned to multiple agents")
            aliases[key]=a['id']
        start = date.fromisoformat(a['start_date']) if a.get('start_date') else None
        end = date.fromisoformat(a['end_date']) if a.get('end_date') else None
        if start and end and end < start:
            raise BdcReportError(f"{a['display_name']}: end date precedes start date")

def _count(value: str, column: str) -> int:
    s=str(value).strip().replace(",", "")
    if not s.isdigit():raise BdcReportError(f"{column} must be a nonnegative integer, got {value!r}")
    return int(s)

def _rate(value: str) -> float | None:
    s=str(value).strip()
    if s in ("", "—", "-"):return None
    try:
        v=float(s.removesuffix("%")) / (100 if s.endswith("%") else 1)
    except ValueError as exc:raise BdcReportError(f"Invalid handoff reply rate: {value!r}") from exc
    if not 0<=v<=1:raise BdcReportError(f"Handoff reply rate out of range: {value!r}")
    return v

def _location(dealer: str) -> str:
    s=str(dealer).casefold()
    for loc in sorted(LOCATIONS,key=len,reverse=True):
        if loc.casefold() in s:return loc
    if "north olmsted" in s or "chrysler" in s:return "CDJR"
    raise BdcReportError(f"Unrecognized dealership: {dealer}")

def _active_for_month(agent:dict, start:date, end:date)->bool:
    a=date.fromisoformat(agent['start_date']) if agent.get('start_date') else None
    b=date.fromisoformat(agent['end_date']) if agent.get('end_date') else None
    return (a is None or a <= end) and (b is None or b >= start)

def process_csv(csv_bytes: bytes, roster: dict, expected_month: str | None = None) -> dict:
    validate_roster(roster)
    try:
        reader=csv.DictReader(io.StringIO(csv_bytes.decode('utf-8-sig')))
        if not reader.fieldnames or REQUIRED-set(reader.fieldnames):
            raise BdcReportError("Missing CSV columns: " + ", ".join(sorted(REQUIRED-set(reader.fieldnames or []))))
        raw=list(reader)
    except UnicodeError as exc:raise BdcReportError("CSV must be UTF-8 encoded") from exc
    if not raw:raise BdcReportError("CSV contains no user rows")
    dates=set()
    for r in raw:
        try:dates.add((date.fromisoformat(r['Start Date']),date.fromisoformat(r['End Date'])))
        except (TypeError,ValueError) as exc:raise BdcReportError("CSV contains invalid Start Date or End Date") from exc
    if len(dates)!=1:raise BdcReportError("CSV contains mixed reporting periods")
    start,end=dates.pop()
    if end<start:raise BdcReportError("CSV end date precedes start date")
    if (start.year,start.month)!=(end.year,end.month):raise BdcReportError("CSV must cover one reporting month")
    month=f"{start:%Y-%m}"
    if expected_month and expected_month !=month:raise BdcReportError(f"Selected {expected_month}, but CSV covers {month}")
    aliases={normalize_name(n):a for a in roster['agents'] for n in a['matador_names']}
    matched=defaultdict(list); excluded=[]; outside=[]
    for r in raw:
        agent=aliases.get(normalize_name(r['User']))
        if agent is None:
            excluded.append(r['User']);continue
        if not _active_for_month(agent,start,end):
            outside.append({'name':r['User'],'agent':agent['display_name']});continue
        loc=_location(r['Dealer'])
        matched[agent['id']].append({'location':loc,'messages':_count(r['Messages Sent'],'Messages Sent'),
            'customers':_count(r['Customers Messaged'],'Customers Messaged'), 'handoffs':_count(r['Handoffs'],'Handoffs'),
            'rate':_rate(r['Handoff Reply Rate'])})
    agents=[]
    for a in roster['agents']:
        entries=matched.get(a['id'],[])
        if not entries:continue
        locations=defaultdict(lambda: {'messages':0,'customers':0,'handoffs':0})
        for e in entries:
            for k,sk in [('messages','messages'),('customers','customers'),('handoffs','handoffs')]:
                locations[e['location']][k]+=e[sk]
        messages=sum(e['messages'] for e in entries)
        customers=sum(e['customers'] for e in entries)
        handoffs=sum(e['handoffs'] for e in entries)
        valid=[e for e in entries if e['rate'] is not None and e['handoffs']>0]
        if len(entries)==1:
            rate=entries[0]['rate'];estimated=False
        elif valid:
            denominator=sum(e['handoffs'] for e in valid)
            rate=sum(e['rate']*e['handoffs'] for e in valid)/denominator
            estimated=True
        else:rate=None;estimated=False
        most=max(locations,key=lambda n:(locations[n]['messages'],n)) if messages else None
        agents.append({'id':a['id'],'name':a['display_name'],'messages':messages,'customers':customers,'handoffs':handoffs,
            'handoffReplyRate':rate,'replyRateEstimated':estimated,'mostMessagedLocation':most,
            'locations':[{'location':name,**metrics} for name,metrics in sorted(locations.items())]})
    return {'month':month,'period_start':start.isoformat(),'period_end':end.isoformat(),
        'agents':agents,'matched_agents':len(agents),'excluded_users':len(excluded),
        'excluded_user_names':sorted(set(excluded)), 'outside_employment':outside,
        'missing_agents':[a['display_name'] for a in roster['agents'] if a['id'] not in matched and _active_for_month(a,start,end)],
        'notes':['For multiple source rows, reply rate is a handoff-weighted estimate from rounded reported rates; not an exact reply count.',
                 'Customers messaged is summed across rows and may count a customer more than once across locations.',
                 'Name matching is exact after case/whitespace normalization; CRM Role is deliberately ignored.']}
