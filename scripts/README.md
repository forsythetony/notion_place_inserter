# `scripts/`

Operational and diagnostic Python (and other) utilities for this repo.

## Layout

- Put new scripts here (including subfolders such as `integration_probes/` or `env_template_compare/`) so tooling stays in one place.

## Dependencies

- **One** [`requirements.txt`](requirements.txt) for all Python scripts under `scripts/`.
- **Do not** add a `requirements.txt` inside subfolders; add packages to the shared [`requirements.txt`](requirements.txt) instead.
- Use **one** virtual environment for scripts work, e.g. from the repo root:

  ```bash
  python -m venv scripts/.venv
  scripts/.venv/bin/pip install -r scripts/requirements.txt
  ```

  The file includes the repo root [`requirements.txt`](../requirements.txt) so imports like `from app.…` work when you run a script with the repo root on `PYTHONPATH` (as the integration probes do).

## Makefile

- [`Makefile`](Makefile): e.g. `make -C scripts probe-google-places` (default query **stone arch bridge Minneapolis**) or override `QUERY=…`; optional `ENV_FILE`, `DETAILS=1`. Runs the probe from the repo root so env paths match the main project.

## See also

- [`envs/env.template`](../envs/env.template) — env vars referenced by the app and many scripts.
