# RFCat Transmitter

Turns the commands in your RFCat manufacturer YAML files into Home Assistant
buttons. Pressing a button transmits that command through a YARD Stick One (or
other RFCat / CC1111 dongle) plugged into the Home Assistant machine.

## Requirements

- Home Assistant OS or Supervised (add-ons are not available on Container or Core installs).
- The Mosquitto broker add-on and the MQTT integration.
- A YARD Stick One or other RFCat dongle on a USB port of the HA machine.

## Setup

1. Add this repository to the add-on store
   (Settings → Add-ons → Add-on store → ⋮ → Repositories):
   `https://github.com/DarwinInnovation/py-rfcat-cli`
2. Install **RFCat Transmitter** and start it.
3. On first start it creates `manufacturers/` in the add-on's config folder
   (`/addon_configs/<id>_rfcat_transmitter/` from the File editor or Samba add-on)
   containing `example.yaml`. Replace it with your own manufacturer files and
   restart the add-on.

Each command appears as a button on a device named after its manufacturer.

## Manufacturer files

Same format as `manufacturers/example.yaml` in the repository. Quote command
names that YAML would read as booleans, such as `"on"`, `"off"`, `"yes"` and
`"no"`; the add-on refuses to start otherwise.

## Options

| Option | Default | Meaning |
| --- | --- | --- |
| `manufacturers_dir` | `/config/manufacturers` | Folder of manufacturer YAML files inside the add-on. |
| `topic_prefix` | `rfcat` | MQTT topics: `<prefix>/tx/<manufacturer>/<command>`, `<prefix>/status`, `<prefix>/result`. |
| `discovery_prefix` | `homeassistant` | HA MQTT discovery prefix. |
| `tx_timeout` | `30` | Seconds before a transmission is treated as failed. |
| `verbose` | `false` | Debug logging. |

## MQTT topics

- `<prefix>/tx/<manufacturer>/<command>`: any payload transmits the command.
- `<prefix>/status`: `online` / `offline` (buttons become unavailable when offline).
- `<prefix>/result`: JSON per transmission, e.g. `{"manufacturer": "example", "command": "cmd1", "status": "sent"}`.

## Notes

- Transmissions are queued and sent one at a time. Each one runs `rfcat-tx-cmd`
  in a fresh process, so a stuck dongle doesn't wedge the add-on.
- If transmissions start failing, unplug and replug the dongle.
- Buttons for commands you remove from the YAML are not deleted automatically
  yet; delete them from the MQTT device page.
