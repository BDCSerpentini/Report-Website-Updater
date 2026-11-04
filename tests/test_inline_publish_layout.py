from pathlib import Path

APP = Path(__file__).resolve().parents[1] / 'src/matador_reporting/app.py'


def test_all_report_pages_publish_before_google_sheets():
    source = APP.read_text()
    for category in ('email', 'dashboard', 'leadSources', 'volie'):
        start = source.index(f'_inline_dashboard_publish("{category}"')
        assert source.index('Google Sheets destination', start) > start
    assert '"Publish to Dashboard",' not in source


def test_publish_confirmation_is_specific_to_current_report_data():
    source = APP.read_text()
    assert 'hashlib.sha256' in source
    assert '"rows": rows' in source
    assert '"location": location' in source
    assert 'disabled=not confirmed' in source
