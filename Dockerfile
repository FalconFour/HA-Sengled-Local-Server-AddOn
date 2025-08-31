# Multi-stage build for Sengled Local Server
ARG BUILD_FROM=ghcr.io/home-assistant/base-python:3.12-alpine3.21
FROM $BUILD_FROM

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install system dependencies
RUN apk add --no-cache \
    mosquitto \
    mosquitto-clients \
    openssl \
    python3 \
    python3-dev \
    py3-pip \
    gcc \
    musl-dev \
    libffi-dev \
    openssl-dev \
    jq \
    curl \
    bash \
    coreutils

# Install Python dependencies
COPY requirements.txt /tmp/
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

# Create directory structure
RUN mkdir -p \
    /app/src \
    /app/mosquitto \
    /app/web \
    /app/scripts \
    /app/certs \
    /data/mosquitto \
    /data/certs \
    /data/config \
    /var/log/mosquitto

# Copy application files
COPY src/ /app/src/
COPY mosquitto/ /app/mosquitto/
COPY web/ /app/web/
COPY scripts/ /app/scripts/
COPY run.sh /app/
COPY translations/ /usr/src/app/translations/

# Set permissions
RUN chmod +x /app/run.sh \
    && chmod +x /app/scripts/*.sh \
    && chown -R root:root /app \
    && chmod -R 755 /app

# Create mosquitto user and set permissions
RUN addgroup -g 1883 mosquitto \
    && adduser -u 1883 -D -G mosquitto mosquitto \
    && chown -R mosquitto:mosquitto /data/mosquitto \
    && chown -R mosquitto:mosquitto /var/log/mosquitto

# Expose ports
EXPOSE 54448 28527

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD /app/scripts/healthcheck.sh

# Set working directory
WORKDIR /app

# Labels for Home Assistant
LABEL \
    io.hass.version="1.0.0" \
    io.hass.type="addon" \
    io.hass.arch="armhf|aarch64|i386|amd64"

# Start the services
CMD ["/app/run.sh"]