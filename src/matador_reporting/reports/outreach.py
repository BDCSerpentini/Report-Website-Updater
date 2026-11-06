"""Validate Matador monthly per-dealer Automations and Broadcasts exports."""
from __future__ import annotations

import calendar
from datetime import date, datetime
from io import BytesIO

import pandas as pd


class OutreachError(ValueError):
    pass


DEALERS = {
    'serpentini chevrolet of medina': 'Medina',
    'serpentini chevrolet of strongsville': 'Strongsville',
    'serpentini chevrolet of tallmadge': 'Tallmadge',
    'serpentini chevrolet of westlake': 'Westlake',
    'serpentini chevrolet of willoughby hills': 'Willoughby',
    'serpentini chevrolet of orrville': 'Orrville',
    'medina': 'Medina', 'strongsville': 'Strongsville', 'tallmadge': 'Tallmadge',
    'westlake': 'Westlake', 'willoughby': 'Willoughby', 'willoughby hills': 'Willoughby',
    'orrville': 'Orrville', 'cdjr': 'CDJR',
    'serpentini chrysler dodge jeep ram north olmsted': 'CDJR',
}

FIELDS = {
    'automations': ('Customers Messaged', 'Customers Engaged', 'Reply Rate', 'AI Influenced Appts', 'Best Automation'),
    'broadcasts': ('Total Broadcasts', 'Customers Messaged', 'Reply Rate', 'Appts Influenced', 'Top Broadcasts'),
}


def _number(value, field: str, *, empty_allowed: bool = False):
    if pd.isna(value) or str(value).strip() in ('', '—', '-', '–'):
        if empty_allowed:
            return None
        raise OutreachError(f'Missing {field}; a blank is not treated as zero.')
    try:
        n = float(str(value).replace(',', '').strip())
    except ValueError as exc:
        raise OutreachError(f'Invalid {field}: {value!r}') from exc
    if not n.is_integer() or n < 0:
        raise OutreachError(f'{field} must be a nonnegative whole number.')
    return int(n)


def _rate(value):
    if pd.isna(value) or str(value).strip() in ('', '—', '-', '–'):
        return None
    raw = str(value).strip()
    try:
        n = float(raw.strip('%')) / (100 if '%' in raw else 1)
    except ValueError as exc:
        raise OutreachError(f'Invalid reply rate: {raw}') from exc
    if not 0 <= n <= 1:
        raise OutreachError('Reply rate must be between 0% and 100%.')
    return n


def parse_outreach_csv(data: bytes, category: str, month: date) -> list[dict]:
    if category not in FIELDS:
        raise OutreachError('Unknown outreach category.')
    try:
        frame = pd.read_csv(BytesIO(data), encoding='utf-8-sig', dtype=str).fillna('')
    except Exception as exc:
        raise OutreachError(f'Cannot read CSV: {exc}') from exc
    required = ('Start Date', 'End Date', 'Dealer', *FIELDS[category])
    missing = [c for c in required if c not in frame.columns]
    if missing:
        raise OutreachError('Missing columns: ' + ', '.join(missing))
    if frame.empty:
        raise OutreachError('This report has no dealership rows.')
    rows, seen = [], set()
    last_day = calendar.monthrange(month.year, month.month)[1]
    for i, r in frame.iterrows():
        try:
            start = pd.to_datetime(r['Start Date']).date()
            end = pd.to_datetime(r['End Date']).date()
        except Exception as exc:
            raise OutreachError(f'Row {i+2}: invalid reporting dates.') from exc
        if (start.year, start.month) != (month.year, month.month) or (end.year, end.month) != (month.year, month.month) or start.day != 1 or end.day != last_day:
            raise OutreachError(f'Row {i+2}: CSV covers {start}–{end}, not the complete selected month {month:%B %Y}.')
        dealer = DEALERS.get(str(r['Dealer']).strip().casefold())
        if not dealer:
            raise OutreachError(f'Row {i+2}: unknown dealership {r["Dealer"]!r}.')
        if dealer in seen:
            raise OutreachError(f'Duplicate dealership {dealer}.')
        seen.add(dealer)
        messaged = _number(r['Customers Messaged'], 'Customers Messaged')
        reply = _rate(r['Reply Rate'])
        if category == 'automations':
            engaged = _number(r['Customers Engaged'], 'Customers Engaged')
            influenced = _number(r['AI Influenced Appts'], 'AI Influenced Appts')
            if engaged > messaged:
                raise OutreachError(f'{dealer}: engaged cannot exceed customers messaged.')
            rows.append({'location': dealer, 'messaged': messaged, 'engaged': engaged,
                         'replyRate': reply, 'influenced': influenced,
                         'bestCampaign': str(r['Best Automation']).strip() or None})
        else:
            count = _number(r['Total Broadcasts'], 'Total Broadcasts', empty_allowed=True)
            influenced = _number(r['Appts Influenced'], 'Appts Influenced')
            rows.append({'location': dealer, 'broadcasts': count, 'messaged': messaged,
                         'replyRate': reply, 'influenced': influenced,
                         'topCampaign': str(r['Top Broadcasts']).strip().strip('—') or None})
    return rows
