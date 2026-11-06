# BDC Agent Performance — month selection

The BDC Agent Performance Streamlit page now includes a Reporting month dropdown, following the other report workflows. It defaults to the month detected from the uploaded Matador Users CSV. A mismatch blocks preview/download/publishing to prevent writing to an incorrect month.

Each published month is stored separately under `reports.json` → `months` → `YYYY-MM` → `bdcAgents`. The GitHub Pages BDC tab already supports selecting available reporting months.

Deploy this Streamlit repository update only; no website ZIP replacement is required for the dropdown.
