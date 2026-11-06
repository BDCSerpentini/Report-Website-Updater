"""Optional persistence for approved BDC roster in the Streamlit source repository.

A separate scoped GitHub token is required to save. The seed roster is read-only fallback.
"""
from __future__ import annotations
import base64
import json
from pathlib import Path
from urllib import parse
from matador_reporting.github_publisher import _github_request, PublishError
from .processor import validate_roster, BdcReportError

SEED = Path(__file__).resolve().parents[4] / 'bdc_agents.json'


def load_seed() -> dict:
    data=json.loads(SEED.read_text(encoding='utf-8'))
    validate_roster(data)
    return data


def _url(owner: str, repo: str, branch: str) -> str:
    q=lambda s:parse.quote(s,safe='')
    return f"https://api.github.com/repos/{q(owner)}/{q(repo)}/contents/bdc_agents.json?ref={q(branch)}"


def fetch_roster(token: str, owner: str, repo: str, branch: str) -> tuple[dict, str]:
    data=_github_request(_url(owner,repo,branch),token)
    try:
        roster=json.loads(base64.b64decode(data['content']).decode('utf-8'))
        validate_roster(roster)
        return roster,data['sha']
    except (KeyError, ValueError, UnicodeError, BdcReportError) as exc:
        raise PublishError('Remote BDC roster is malformed; no changes were made') from exc


def save_roster(roster: dict, token: str, owner: str, repo: str, branch: str, sha: str) -> None:
    validate_roster(roster)
    if not sha:raise PublishError('Roster must be loaded from GitHub before editing remotely')
    q=lambda s:parse.quote(s,safe='')
    url=f"https://api.github.com/repos/{q(owner)}/{q(repo)}/contents/bdc_agents.json"
    body={'message':'Update approved BDC agent roster','content':base64.b64encode((json.dumps(roster,indent=2)+'\n').encode()).decode(), 'branch':branch,'sha':sha}
    _github_request(url,token,'PUT',body)
