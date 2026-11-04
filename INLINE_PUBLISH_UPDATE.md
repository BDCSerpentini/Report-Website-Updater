# Inline Publish to Dashboard update — November 2026

The separate **Publish to Dashboard** Streamlit page has been removed. Each of the four report pages now shows **Publish to Quarterly Dashboard** directly above **Google Sheets destination**, after the report has been generated:

- Email Template Performance (publishes selected dealership only)
- Matador Dashboard
- Lead Source Performance
- Volie SMS Service Appointments

Use **Review dashboard data before publishing**, approve the public-data confirmation, then click **Add / Update Quarterly Dashboard**. This is an explicit action, not automatic publishing. It updates only that report's month/category in `bdcserpentini/serpentini-reports` `reports.json` (email only selected dealership), using the existing `[github]` Streamlit Secrets. No tokens are included in this ZIP.

To update the existing repository: extract the ZIP; copy all its *contents* into the cloned `Report-Website-Updater` working folder alongside `.git`, preserving subfolders; then run `git add -A`, `git status` (check for secrets), `git commit -m "Move dashboard publishing into report pages"`, `git push origin main`. The Streamlit app's entry point remains `app.py`.

Test status: Python compilation succeeds and 13 relevant publishing/email tests pass. The full suite cannot run in this environment because Streamlit is not installed here. After GitHub deployment, verify each inline button and dashboard refresh in Streamlit.
