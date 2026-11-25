FROM --platform=linux/amd64 debian:12.12-slim@sha256:d5d3f9c23164ea16f31852f95bd5959aad1c5e854332fe00f7b3a20fcc9f635c

LABEL org.opencontainers.image.source="https://github.com/brondani/demo-creator"

# Debian's dated archive fixes package selection; the upstream editor is hash checked.
ARG DEBIAN_SNAPSHOT=20260101T000000Z
RUN rm -f /etc/apt/sources.list.d/debian.sources \
 && printf 'deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/%s/ bookworm bookworm-updates main\n' "$DEBIAN_SNAPSHOT" > /etc/apt/sources.list \
 && printf 'deb [check-valid-until=no] http://snapshot.debian.org/archive/debian-security/%s/ bookworm-security main\n' "$DEBIAN_SNAPSHOT" >> /etc/apt/sources.list \
 && apt-get -o Acquire::Check-Valid-Until=false update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates curl ffmpeg flite libasound2 libatk-bridge2.0-0 libatk1.0-0 \
      libcups2 libdbus-1-3 libdrm2 libgbm1 libglib2.0-0 libgtk-3-0 \
      libnss3 libx11-xcb1 libxcomposite1 libxdamage1 libxfixes3 libxkbcommon0 \
      libxrandr2 openbox python3 python3-pip xauth xdotool xvfb \
 && rm -rf /var/lib/apt/lists/*

ARG CODIUM_VERSION=1.105.17075
ARG CODIUM_SHA256=f9a31c44033598ebb6acb0951ad93280680cffc54d7ad78ceba04e9664022290
RUN curl -fsSL --retry 3 "https://github.com/VSCodium/vscodium/releases/download/${CODIUM_VERSION}/VSCodium-linux-x64-${CODIUM_VERSION}.tar.gz" -o /tmp/codium.tar.gz \
 && echo "${CODIUM_SHA256}  /tmp/codium.tar.gz" | sha256sum -c - \
 && mkdir -p /opt/codium \
 && tar -xzf /tmp/codium.tar.gz -C /opt/codium \
 && rm /tmp/codium.tar.gz

COPY requirements-renderer.txt /opt/demo/requirements-renderer.txt
RUN pip3 install --break-system-packages --no-cache-dir --only-binary=:all: \
      --require-hashes -r /opt/demo/requirements-renderer.txt
COPY renderer.py /opt/demo/renderer.py
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin demo
USER demo
ENV HOME=/home/demo
WORKDIR /work
