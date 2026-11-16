ARG BUILD_FROM
FROM ${BUILD_FROM}

# libusb for pyusb (used by rflib), git to fetch py-rfcat-cli.
RUN apk add --no-cache libusb git

# The add-on build context is this folder only, so the CLI code is fetched
# from GitHub. Override RFCAT_CLI_REF (branch or tag) to build another version.
ARG RFCAT_CLI_REF=main
RUN git clone --depth 1 --branch "${RFCAT_CLI_REF}" \
        https://github.com/DarwinInnovation/py-rfcat-cli /opt/py-rfcat-cli \
    && pip install --no-cache-dir pyyaml paho-mqtt rfcat

COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD ["/run.sh"]
