# Streamlit deployment

This archive repairs the flattened files in the original GitHub repository.

1. Replace the repository contents with this archive **preserving folders**.
2. Keep Streamlit Main file path set to `app.py`.
3. Keep `requirements.txt` at the root.
4. Set GitHub credentials only in Streamlit Cloud Secrets, never in repository code.
5. Reboot/redeploy the app.

The root `app.py` appends `src` to the import path and invokes the package entrypoint.
