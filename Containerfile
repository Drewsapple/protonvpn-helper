FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://repo.protonvpn.com/debian/public_key.asc | gpg --dearmor -o /etc/apt/keyrings/proton.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/proton.gpg] https://repo.protonvpn.com/debian unstable main" \
      > /etc/apt/sources.list.d/protonvpn.list

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-proton-vpn-api-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY list_servers.py /app/list_servers.py

CMD ["python3", "/app/list_servers.py"]
