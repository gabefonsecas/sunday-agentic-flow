# Contributing

Use Python 3.11 or newer.
Create branches from `main`.
Keep the runtime dependency-free when practical.
Never embed provider credentials or user IDs.

Run before opening a pull request:

```bash
python3 -m compileall -q sunday scripts tests
python3 -m unittest discover -s tests -v
python3 scripts/check_model_routing.py
python3 scripts/sync_versions.py
```

Update `VERSION` and `CHANGELOG.md` for releases.
Keep every host manifest synchronized.
