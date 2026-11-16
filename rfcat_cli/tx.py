import logging
import os
import time

import rflib
import yaml

from .manufacturer import Manufacturer


DEFAULT_MANUFACTURER_DIR = "/etc/rfcat-cli/manufacturers"


def load_manu_yaml(path):
    logging.info("Loading %s", path)

    with open(path, "r", encoding="utf-8") as infile:
        return yaml.safe_load(infile)


def load_manufacturers(manufacturer_dir=DEFAULT_MANUFACTURER_DIR, manu_path=None):
    manufacturers = {}

    if manu_path:
        mcfg = load_manu_yaml(manu_path)
        manufacturers[mcfg["name"].lower()] = Manufacturer(mcfg)
        return manufacturers

    for entry in os.scandir(manufacturer_dir):
        if entry.name.endswith(".yaml") and entry.is_file():
            mcfg = load_manu_yaml(entry.path)
            manufacturers[mcfg["name"].lower()] = Manufacturer(mcfg)

    return manufacturers


def transmit_command(manufacturer, command, manufacturer_dir=DEFAULT_MANUFACTURER_DIR, manu_path=None):
    manufacturers = load_manufacturers(manufacturer_dir=manufacturer_dir, manu_path=manu_path)

    rfcat = rflib.RfCat()
    time.sleep(0.1)
    rfcat.setModeIDLE()
    time.sleep(0.1)

    manu = manufacturers[manufacturer.lower()]
    manu.setup(rfcat)
    time.sleep(0.1)
    manu.tx_cmd(rfcat, command.lower())

    rfcat.setModeIDLE()
    time.sleep(0.1)
