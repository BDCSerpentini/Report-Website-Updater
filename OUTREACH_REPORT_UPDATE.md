# Automations & Broadcasts (November 2026)

In Streamlit, open **Automations & Broadcasts**, select the reporting month, then upload one or both Matador per-dealer CSV exports. Automations and Broadcasts have separate preview/publish controls. Review each report and select **Add / Update Quarterly Dashboard** to publish that category into the existing `reports.json` on GitHub. GitHub credentials remain in Streamlit secrets; never commit a token.

Reports must cover the complete selected calendar month. An unknown dealership, duplicate dealership, invalid percentage/count, or mismatched month blocks publication. Missing broadcast counts remain null, not zero. Publishing category `automations` only changes `months[YYYY-MM].automations`; `broadcasts` changes only `months[YYYY-MM].broadcasts`. The publisher preserves all existing categories and months.

Website: use the separately provided updated `index.html` in the GitHub Pages repo. The October 2026 outreach data are embedded as fallback for initial viewing. Later monthly outreach data are loaded from `reports.json` as published by Streamlit.
