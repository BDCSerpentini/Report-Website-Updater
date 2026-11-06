# BDC Agent Reporting — initial release

## New Streamlit pages

- **Manage BDC Agents** — edit the approved roster, add names, configure effective dates, export a backup JSON; optionally save roster changes to GitHub.
- **BDC Agent Performance** — upload one monthly `Users - All Users` CSV, match only roster names, review excluded users and preview every BDC agent's messages, customers messaged, handoffs, reply rate, and most messaged location. Download a CSV or JSON report.

The roster is seeded with 21 agents from the previously approved July BDC list. **Noah** replaces **Woah** as the display name. Names marked `start_date: null` and `end_date: null` have unknown employment dates and remain eligible for any reporting month until the operator sets those dates. Do not treat the initial file as authoritative for current employment status. Never delete a departing agent: enter the final employment date, preserving historical eligibility. For a returning employee, handle separate employment periods before relying on fully precise gap exclusions.

## Safe persistence

Bundled `bdc_agents.json` is readable without any secrets, but writes to an application container do **not** persist across Streamlit Cloud restarts.

Option A: Use **Download roster JSON**, replace `bdc_agents.json` in the Streamlit GitHub repository, and commit/push the file. This is the default and needs no new tokens.

Option B: Give Streamlit a GitHub token with **Contents: Read and write** access to the **Report-Website-Updater** repository only. Set the following in Streamlit Secrets (NOT in GitHub):

```toml
[bdc_roster_github]
token = "YOUR_SCOPED_TOKEN"
owner = "BDCSerpentini"
repository = "Report-Website-Updater"
branch = "main"
```

If the token works, the manager fetches the latest roster and can save edited data with an existing file SHA. Remote save failures do not overwrite the local file. **Do not reuse the token scoped to `serpentini-reports` without checking its repository permissions.**

## Rules and limitations

- Matching uses case- and whitespace-normalized *full Matador name* aliases, never the CSV's Role field. Ambiguous names cannot be assigned to multiple agents. Roster agents missing from an export are reported, not given invented activity.
- Effective dates are inclusive and compare with the upload's month/date range. A mid-month departure still qualifies that month's whole monthly row, because this report does not contain daily breakdowns. This is a month-level inclusion/exclusion rule, not daily filtering.
- Exact handoff reply rate is copied for a single source row. If the same employee appears multiple times, a weighted approximation based on rounded row rates and handoffs is calculated and clearly flagged; the CSV contains no exact reply count. Customers messaged may be double-counted across locations.
- The exported JSON uses `{ "month": "YYYY-MM", "bdcAgents": [...] }` as a proposed monthly data format. **Automatic publishing to the public GitHub Pages dashboard is NOT enabled in this phase.** The existing dashboard BDC tab currently uses a static July snapshot. That tab must be updated to read per-month `bdcAgents` data before live publishing makes sense.
- Your Streamlit source repository may be public. The roster contains agent names; verify company policy before committing it. **Never add full employee exports, any token, or `secrets.toml` to the public repository.**
