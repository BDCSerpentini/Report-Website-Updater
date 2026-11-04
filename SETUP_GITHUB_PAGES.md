# Publish to GitHub Pages — setup

## One-time GitHub Pages update

1. Open the `Serpentini_GitHub_Pages_Ready` folder from the companion ZIP.
2. Upload **both** `index.html` and `reports.json` to the root of `bdcserpentini/serpentini-reports` on branch `main`, replacing the existing `index.html`.
3. Keep `reports.json` in the same folder as `index.html`. It starts with the existing July–October data and all corrected Orrville/CDJR email figures.
4. Once GitHub Pages deploys, verify that `https://bdcserpentini.github.io/serpentini-reports/reports.json` loads a JSON document.

## GitHub access token (app only, NEVER in HTML)

On GitHub, create a **fine-grained personal access token** scoped to this one repository with **Contents: Read and write** permission. Use the minimum expiration your organization permits, and store it only on the machine/server running Streamlit.

Create a local `.streamlit/secrets.toml` inside the reporting app (or use Streamlit's secure cloud secret settings) and add:

```toml
[github]
token = "YOUR_FINE_GRAINED_TOKEN"
owner = "bdcserpentini"
repository = "serpentini-reports"
branch = "main"
```

Do not commit secrets.toml, share it in a ZIP, or put your token in the website. `.gitignore` excludes it.

## Monthly workflow

1. Generate and review a Matador Dashboard, Lead Source, Email Template or Volie report in Streamlit.
2. Open **Publish to Dashboard** in the sidebar, select the completed report and review the preview.
3. Check the approval box, then click **Publish to Dashboard**. Only that report category and month are changed; email updates target only the selected dealership.
4. Wait for GitHub Pages to deploy, then refresh the published dashboard.

Each report is published separately. Publishing does not upload raw CSVs. No GitHub token is transmitted to the site; the token remains on the Streamlit server.

## Important limits

- **Your current GitHub Pages site is PUBLIC.** Anyone can access reports.json and all published metrics. Use company-approved aggregate data only, or move to authenticated hosting.
- GitHub Pages does not provide a database. This saves a versioned JSON file in GitHub (commit history provides an audit trail).
- Publishing updates GitHub, not the browser's local storage. On the public website, published categories take precedence over local browser edits after refresh. Browser-only fields, including optional broadcasts, are not automatically published.
- Generating one Email Template report for one dealership does not update the other dealerships. Publish each dealership separately.
- The public website falls back to embedded data if reports.json cannot be fetched (for example, opening index.html directly as a file).
- August/September/Orrville and October/CDJR corrections are retained in the starter data.
