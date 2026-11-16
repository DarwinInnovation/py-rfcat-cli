#!/usr/bin/with-contenv bashio
set -e

MANU_DIR="$(bashio::config 'manufacturers_dir')"
if ! bashio::fs.directory_exists "${MANU_DIR}"; then
    bashio::log.info "Creating ${MANU_DIR} with the example manufacturer file"
    mkdir -p "${MANU_DIR}"
    cp /opt/py-rfcat-cli/manufacturers/example.yaml "${MANU_DIR}/"
fi

if ! bashio::services.available mqtt; then
    bashio::exit.nok "No MQTT broker found. Install the Mosquitto broker add-on and the MQTT integration."
fi

MQTT_HOST="$(bashio::services mqtt 'host')"
MQTT_PORT="$(bashio::services mqtt 'port')"
export RFCAT_MQTT_USER="$(bashio::services mqtt 'username')"
export RFCAT_MQTT_PASSWORD="$(bashio::services mqtt 'password')"

ARGS=(
    --mqtt-host "${MQTT_HOST}"
    --mqtt-port "${MQTT_PORT}"
    --topic-prefix "$(bashio::config 'topic_prefix')"
    --discovery-prefix "$(bashio::config 'discovery_prefix')"
    --tx-timeout "$(bashio::config 'tx_timeout')"
    -d "${MANU_DIR}"
)
if bashio::config.true 'verbose'; then
    ARGS+=(-v)
fi

# rfcat-tx-cmd writes its log to the working directory.
cd /data
bashio::log.info "Starting RFCat MQTT bridge (broker ${MQTT_HOST}:${MQTT_PORT})"
exec python3 /opt/py-rfcat-cli/rfcat-mqtt-bridge "${ARGS[@]}"
