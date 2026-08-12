# Contributing

Use Python 3.11 or newer. Invoke local scripts with `python3.11`.
Do not change the operating system's `python3` command.
Create branches from `main`.
Keep the runtime dependency-free when practical.
Never embed provider credentials or user IDs.

Run before opening a pull request:

```bash
python3.11 -m compileall -q sunday scripts tests
python3.11 -m unittest discover -s tests -v
python3.11 scripts/check_model_routing.py
python3.11 scripts/sync_versions.py
```

Update `VERSION` and `CHANGELOG.md` for releases.
Keep every host manifest synchronized.
