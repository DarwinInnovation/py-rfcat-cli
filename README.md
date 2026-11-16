# py-rfcat-cli

Lightweight command and HTTP service wrappers around `rfcat` for transmitting predefined RF commands from manufacturer YAML definitions.

## What this repo provides

- `rfcat-tx-cmd`: one-shot CLI transmitter
- `rfcat-tx-service`: HTTP service exposing `GET /tx/<manufacturer>/<cmd>`
- `rfcat_cli/`: core Python modules for loading manufacturer configs and transmitting
- `manufacturers/`: example manufacturer YAML files
- `tests/`: unit tests for the HTTP route behavior
- `ecosystem.config.js`: PM2 config for running the service
- `etc/udev/rules.d/20-rfcat.rules`: udev rules granting the `dialout` group access to RFCat devices

## Prerequisites

- Linux
- Python 3.10+
- A local clone of `rfcat` alongside this repo (`../rfcat`)
- Compatible RFCat hardware and permissions (for real transmissions)

## Local virtual environment setup

Use a local `.venv` in this repository. From the repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install pyyaml
python -m pip install -r ../rfcat/requirements.txt
python -m pip install -e ../rfcat
```

If `.venv` already exists, only activate it:

```bash
source .venv/bin/activate
```

## USB permissions

Install the udev rules and add your user to `dialout`:

```bash
sudo cp etc/udev/rules.d/20-rfcat.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo usermod -aG dialout $USER  # then log out and back in
```

## Run the CLI transmitter

```bash
./rfcat-tx-cmd -d manufacturers example cmd1
```

Useful options:

- `-d, --dir`: directory containing manufacturer YAML files
- `-m, --manu`: use a single manufacturer YAML file

## Run the HTTP service

```bash
./rfcat-tx-service --host 0.0.0.0 --port 8080 -d manufacturers -v
```

Each request runs `rfcat-tx-cmd` in a subprocess, so the RFCat dongle is opened and released per transmission rather than held by the long-running service.

Useful options:

- `-d, --dir` / `-m, --manu`: as for `rfcat-tx-cmd`
- `--tx-cli`: path to the `rfcat-tx-cmd` executable (defaults to the one in this repo)
- `--tx-timeout`: seconds to wait for `rfcat-tx-cmd` before failing (default 30)

Then call the endpoint:

```bash
curl http://127.0.0.1:8080/tx/example/cmd1
```

Expected success response:

```json
{
  "manufacturer": "example",
  "command": "cmd1",
  "status": "sent"
}
```

### Running under PM2

```bash
pm2 start ecosystem.config.js
```

The PM2 config checks the user is in `dialout`, activates `.venv` and serves `manufacturers/` on port 8080.

## Run tests

```bash
source .venv/bin/activate
python -m unittest tests/test_service.py
```

## Notes

- Default manufacturer path is `/etc/rfcat-cli/manufacturers`.
- Service logs are written to `rfcat-tx-service.log`.
- CLI logs are written to `rfcat-tx-cmd.log`.
