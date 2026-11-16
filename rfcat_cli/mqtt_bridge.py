"""MQTT bridge exposing manufacturer commands to Home Assistant.

Each command in the manufacturer YAML files becomes a Home Assistant
``button`` entity via MQTT discovery. Pressing the button publishes to
``<prefix>/tx/<manufacturer>/<command>``; the bridge then transmits by
running ``rfcat-tx-cmd`` in a subprocess, exactly like the HTTP service, so
the dongle is only held for the duration of a transmission.
"""

import argparse
import json
import logging
import os
import queue
import re
import threading

import yaml

from .service import DEFAULT_TX_CLI_PATH, transmit_via_cli
from .tx import DEFAULT_MANUFACTURER_DIR


DEFAULT_TOPIC_PREFIX = "rfcat"
DEFAULT_DISCOVERY_PREFIX = "homeassistant"
PAYLOAD_ONLINE = "online"
PAYLOAD_OFFLINE = "offline"


def _slug(value):
    return re.sub(r"[^a-z0-9_]+", "_", str(value).lower()).strip("_")


def load_command_catalog(manufacturer_dir=DEFAULT_MANUFACTURER_DIR, manu_path=None):
    """Read manufacturer YAML for names and descriptions only.

    Returns ``{manufacturer_key: {"name", "freq", "commands": {cmd: desc}}}``.
    Keys match what ``transmit_command`` looks up (manufacturer name lowered).
    The radio is not touched here.
    """
    paths = []
    if manu_path:
        paths.append(manu_path)
    else:
        for entry in sorted(os.scandir(manufacturer_dir), key=lambda e: e.name):
            if entry.name.endswith(".yaml") and entry.is_file():
                paths.append(entry.path)

    catalog = {}
    for path in paths:
        with open(path, "r", encoding="utf-8") as infile:
            cfg = yaml.safe_load(infile) or {}
        key = cfg["name"].lower()
        commands = {}
        for cmd in cfg.get("commands") or []:
            if not isinstance(cmd["name"], str):
                # YAML 1.1 turns bare on/off/yes/no into booleans.
                raise ValueError(f"{path}: command name {cmd['name']!r} must be a string; quote it in the YAML")
            commands[cmd["name"]] = cmd.get("desc", cmd["name"])
        catalog[key] = {
            "name": cfg["name"],
            "freq": (cfg.get("radio") or {}).get("freq"),
            "commands": commands,
        }
    return catalog


def discovery_messages(catalog, topic_prefix=DEFAULT_TOPIC_PREFIX, discovery_prefix=DEFAULT_DISCOVERY_PREFIX):
    """Yield ``(topic, payload_dict)`` HA MQTT discovery configs, one button per command."""
    availability_topic = f"{topic_prefix}/status"
    for manu_key, manu in catalog.items():
        device = {
            "identifiers": [f"rfcat_{_slug(manu_key)}"],
            "name": manu["name"],
            "manufacturer": "RFCat",
        }
        if manu["freq"]:
            device["model"] = f"{manu['freq'] / 1e6:g} MHz"
        for cmd, desc in manu["commands"].items():
            unique_id = f"rfcat_{_slug(manu_key)}_{_slug(cmd)}"
            payload = {
                "name": desc,
                "unique_id": unique_id,
                "command_topic": f"{topic_prefix}/tx/{manu_key}/{cmd}",
                "payload_press": "PRESS",
                "availability_topic": availability_topic,
                "payload_available": PAYLOAD_ONLINE,
                "payload_not_available": PAYLOAD_OFFLINE,
                "device": device,
            }
            yield f"{discovery_prefix}/button/{unique_id}/config", payload


def parse_tx_topic(topic, topic_prefix=DEFAULT_TOPIC_PREFIX):
    """Return ``(manufacturer, command)`` for ``<prefix>/tx/<m>/<c>``, else ``(None, None)``."""
    base = f"{topic_prefix}/tx/"
    if not topic.startswith(base):
        return None, None
    parts = topic[len(base):].split("/")
    if len(parts) != 2 or not all(parts):
        return None, None
    return parts[0], parts[1]


class Bridge:
    """Glue between an MQTT client and a serialised transmit worker."""

    def __init__(self, client, catalog, transmit, topic_prefix=DEFAULT_TOPIC_PREFIX,
                 discovery_prefix=DEFAULT_DISCOVERY_PREFIX):
        self.client = client
        self.catalog = catalog
        self.transmit = transmit
        self.topic_prefix = topic_prefix
        self.discovery_prefix = discovery_prefix
        self.jobs = queue.Queue()

    def on_connect(self, client, _userdata, _flags, reason_code, _properties=None):
        if getattr(reason_code, "is_failure", False):
            logging.error("MQTT connect failed: %s", reason_code)
            return
        logging.info("Connected to MQTT broker")
        for topic, payload in discovery_messages(self.catalog, self.topic_prefix, self.discovery_prefix):
            client.publish(topic, json.dumps(payload), qos=1, retain=True)
        client.subscribe(f"{self.topic_prefix}/tx/+/+", qos=1)
        client.publish(f"{self.topic_prefix}/status", PAYLOAD_ONLINE, qos=1, retain=True)

    def on_message(self, _client, _userdata, msg):
        manufacturer, command = parse_tx_topic(msg.topic, self.topic_prefix)
        if manufacturer is None:
            return
        # Queue rather than transmit inline so the MQTT network loop keeps running.
        self.jobs.put((manufacturer, command))

    def process_one(self, manufacturer, command):
        result = {"manufacturer": manufacturer, "command": command}
        known = self.catalog.get(manufacturer.lower(), {}).get("commands", {})
        if command not in known:
            result.update(status="error", error="unknown manufacturer or command")
        else:
            try:
                self.transmit(manufacturer, command)
                result["status"] = "sent"
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logging.exception("Transmit failed")
                result.update(status="error", error=str(exc))
        logging.info("tx %s/%s: %s", manufacturer, command, result["status"])
        self.client.publish(f"{self.topic_prefix}/result", json.dumps(result), qos=1)
        return result

    def worker(self):
        while True:
            manufacturer, command = self.jobs.get()
            try:
                self.process_one(manufacturer, command)
            finally:
                self.jobs.task_done()


def main():
    import paho.mqtt.client as mqtt  # pylint: disable=import-outside-toplevel

    parser = argparse.ArgumentParser(description="Expose RFCat commands to Home Assistant over MQTT")
    parser.add_argument("--mqtt-host", default="localhost")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--mqtt-user", default=os.environ.get("RFCAT_MQTT_USER"))
    parser.add_argument("--mqtt-password", default=os.environ.get("RFCAT_MQTT_PASSWORD"),
                        help="defaults to $RFCAT_MQTT_PASSWORD")
    parser.add_argument("--topic-prefix", default=DEFAULT_TOPIC_PREFIX)
    parser.add_argument("--discovery-prefix", default=DEFAULT_DISCOVERY_PREFIX)
    parser.add_argument("-d", "--dir", default=DEFAULT_MANUFACTURER_DIR,
                        help="directory containing manufacturer YAML files")
    parser.add_argument("-m", "--manu", help="use a single manufacturer file")
    parser.add_argument("--tx-cli", default=str(DEFAULT_TX_CLI_PATH))
    parser.add_argument("--tx-timeout", type=int, default=30)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    catalog = load_command_catalog(args.dir, args.manu)
    logging.info("Loaded %d manufacturer(s), %d command(s)", len(catalog),
                 sum(len(m["commands"]) for m in catalog.values()))

    def _transmit(manufacturer, command):
        transmit_via_cli(manufacturer, command, manufacturer_dir=args.dir, manu_path=args.manu,
                         cli_path=args.tx_cli, timeout=args.tx_timeout)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="rfcat-mqtt-bridge")
    if args.mqtt_user:
        client.username_pw_set(args.mqtt_user, args.mqtt_password)
    client.will_set(f"{args.topic_prefix}/status", PAYLOAD_OFFLINE, qos=1, retain=True)

    bridge = Bridge(client, catalog, _transmit, args.topic_prefix, args.discovery_prefix)
    client.on_connect = bridge.on_connect
    client.on_message = bridge.on_message

    threading.Thread(target=bridge.worker, daemon=True).start()
    # connect_async + retry_first_connection: keep retrying if the broker starts after us.
    client.connect_async(args.mqtt_host, args.mqtt_port)
    client.loop_forever(retry_first_connection=True)


if __name__ == "__main__":
    main()
