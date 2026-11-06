"""Manual GitHub Pages reporting publisher. Never expose token in client-side HTML."""
from __future__ import annotations

import base64
import json
from datetime import date
from urllib import error, parse, request

CATEGORIES = ("dashboard", "leadSources", "email", "volie", "bdcAgents")


class PublishError(Exception):
    """Safe, actionable publishing error."""


def reporting_month_key(value: date) -> str:
    return value.strftime("%Y-%m")


def serialize_report(category: str, result, *, location: str | None = None) -> list[dict]:
    """Translate reviewed Streamlit results into the existing dashboard's schema."""
    if category == "bdcAgents":
        if not isinstance(result, dict) or not isinstance(result.get("agents"), list):
            raise PublishError("Expected validated BDC report data")
        return result["agents"]
    if category == "dashboard":
        return [{"location": r.location, "leads": r.leads, "engaged": r.engaged_contacts,
                 "appointments": r.total_appointments, "influenced": r.ai_influenced_appointments}
                for r in result.locations if r.location != "Total"]
    if category == "leadSources":
        return [{"rank": r.rank, "source": r.lead_source, "dealers": r.dealers,
                 "leads": r.leads, "engaged": r.engaged_leads,
                 "influenced": r.ai_influenced_appointments,
                 "userAppointments": r.user_appointments,
                 "aiAppointments": r.ai_appointments, "loopIns": r.team_loop_ins}
                for r in result.top_sources]
    if category == "email":
        if not location or not result.location_metrics:
            raise PublishError("An email report location and its summary are required.")
        rows = [{"location": location, "campaign": r.reporting_group,
                 "sent": r.emails_sent, "opens": r.emails_opened,
                 "cta": r.cta_users}
                for r in result.campaigns]
        totals = result.location_metrics
        rows.append({"location": location, "campaign": "Location Total",
                     "sent": totals.emails_sent, "opens": totals.emails_opened,
                     "cta": totals.unique_cta_users})
        return rows
    if category == "volie":
        return [{"location": r.location, "clicks": r.bitly_clicks,
                 "users": r.active_users} for r in result.locations]
    raise PublishError("Unknown report category")


def merge_report(document: dict, month: str, category: str, rows: list[dict], *, location: str | None = None) -> dict:
    """Replace only one month's one report; emails update only one dealership."""
    if category not in CATEGORIES or not isinstance(rows, list):
        raise PublishError("Invalid report category or report rows")
    if len(month) != 7 or month[4] != '-' or not (month[:4].isdigit() and month[5:].isdigit() and 1 <= int(month[5:]) <= 12):
        raise PublishError("Invalid reporting month")
    if document.get('schema_version') != 1 or not isinstance(document.get('months'),dict):
        raise PublishError("Unexpected reports.json format; publication cancelled to avoid losing data")
    if category == "bdcAgents":
        ids = set()
        for r in rows:
            if not isinstance(r, dict) or not isinstance(r.get('id'), str) or not r['id'].strip():
                raise PublishError('Each BDC agent requires a stable ID')
            if r['id'] in ids:
                raise PublishError('Duplicate BDC agent ID in report')
            ids.add(r['id'])
            if not isinstance(r.get('name'), str) or not r['name'].strip():
                raise PublishError('Missing BDC agent display name')
            if any(not isinstance(r.get(k), int) or isinstance(r.get(k), bool) or r[k] < 0
                   for k in ('messages', 'customers', 'handoffs')):
                raise PublishError('Invalid BDC counts')
            rate = r.get('handoffReplyRate')
            if rate is not None and (not isinstance(rate, (int, float)) or isinstance(rate, bool) or not 0 <= rate <= 1):
                raise PublishError('BDC reply rates must range from zero to one')
            if not isinstance(r.get('locations'), list) or not isinstance(r.get('replyRateEstimated'), bool):
                raise PublishError('Missing BDC location breakdown or reply-rate metadata')
    doc=json.loads(json.dumps(document))
    monthly=doc['months'].setdefault(month,{})
    if not isinstance(monthly,dict):raise PublishError("Malformed existing month")
    if category=='email':
        if not location:raise PublishError("Missing location for email update")
        if any(r.get('location')!=location for r in rows):
            raise PublishError("Email export contains another dealership")
        prior=monthly.get('email',[])
        if not isinstance(prior,list):raise PublishError("Malformed existing email records")
        monthly['email']=[r for r in prior if r.get('location') != location]+rows
    else:
        monthly[category]=rows
    return doc


def _github_request(url: str, token: str, method: str='GET', data: dict | None=None):
    if not token or not token.strip():raise PublishError("GitHub token is not configured")
    encoded=json.dumps(data).encode('utf-8') if data is not None else None
    req=request.Request(url,data=encoded,method=method,headers={
        'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json',
        'X-GitHub-Api-Version':'2022-11-28','User-Agent':'Serpentini-Reporting-Publisher',
        'Content-Type':'application/json'})
    try:
        with request.urlopen(req,timeout=20) as response:
            return json.loads(response.read())
    except error.HTTPError as exc:
        if exc.code==401:msg='GitHub rejected the token (401). Check its value.'
        elif exc.code==403:msg='GitHub denied access (403). Grant repository Contents: Read and write.'
        elif exc.code==404:msg='reports.json or repository not found (404). Upload the starter reports.json and verify the owner/repository/branch.'
        elif exc.code in (409,422):msg='GitHub changed the file during publication. Refresh and retry; no overwrite was performed.'
        else:msg=f'GitHub returned HTTP {exc.code}.'
        raise PublishError(msg) from exc
    except (error.URLError,TimeoutError) as exc:
        raise PublishError('Cannot reach GitHub. Check network access and try again.') from exc


def publish_report(token: str, owner: str, repository: str, branch: str, month: str, category: str,
                   rows: list[dict], *, location: str | None = None, path: str='reports.json') -> str:
    """Fetch latest JSON, merge selected report, then commit with SHA precondition."""
    if not owner or not repository or not branch or path != 'reports.json':
        raise PublishError('Invalid GitHub settings')
    quote=lambda x:parse.quote(x,safe='')
    url=f'https://api.github.com/repos/{quote(owner)}/{quote(repository)}/contents/{path}?ref={quote(branch)}'
    old=_github_request(url,token)
    if not isinstance(old,dict) or old.get('type')!='file' or not old.get('sha'):
        raise PublishError('GitHub did not return a versioned reports.json file')
    try:
        raw=base64.b64decode(old['content'].replace('\n','')).decode('utf-8')
        original=json.loads(raw)
    except (KeyError,ValueError,UnicodeError) as exc:
        raise PublishError('Cannot decode the published reports.json. File left unchanged.') from exc
    updated=merge_report(original,month,category,rows,location=location)
    if updated==original:return 'Already up to date — no GitHub commit needed'
    content=base64.b64encode((json.dumps(updated,ensure_ascii=False,indent=2)+'\n').encode()).decode()
    commit_url=f'https://api.github.com/repos/{quote(owner)}/{quote(repository)}/contents/{path}'
    result=_github_request(commit_url,token,'PUT',{'message':f'Update {category} {location or ""} {month}'.strip(),
                                                  'content':content,'sha':old['sha'],'branch':branch})
    commit=result.get('commit',{})
    return f'Published successfully: {commit.get("html_url", "GitHub commit created")}'
