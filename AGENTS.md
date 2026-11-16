# AGENTS

Local agent instructions for this repository.

## Environment

- Always use the local virtual environment at `.venv`.
- Never rely on global Python packages.
- Start all Python work from the repo root with:

```bash
source .venv/bin/activate
```

If `.venv` does not exist:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install pyyaml paho-mqtt
python -m pip install -r ../rfcat/requirements.txt
python -m pip install -e ../rfcat
```

## Validation commands

Run these after code changes:

```bash
source .venv/bin/activate
python -m unittest discover -s tests
```

Optional smoke checks:

```bash
./rfcat-tx-cmd -d manufacturers example cmd1
./rfcat-tx-service -v -d manufacturers
```

## Code guidance

- Keep service routing behavior compatible with `GET /tx/<manufacturer>/<cmd>`.
- Reuse `rfcat_cli/tx.py` for transmission logic instead of duplicating it.
- `rfcat-mqtt-bridge` must keep transmitting through `rfcat-tx-cmd` subprocesses, like the HTTP service.
- The Home Assistant add-on lives in `rfcat_transmitter/`; bump its `version` in `config.yaml` when its behaviour changes.
- Keep YAML manufacturer files in `manufacturers/` for local testing.
