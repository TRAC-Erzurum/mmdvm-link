FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# mosquitto_passwd is required by mmdvm-link/server/core/installer_gen.py
RUN apt-get update \
    && apt-get install -y --no-install-recommends mosquitto \
    && rm -rf /var/lib/apt/lists/*

COPY mmdvm-link/requirements.txt /app/mmdvm-link/requirements.txt
RUN pip install --no-cache-dir -r /app/mmdvm-link/requirements.txt

COPY mmdvm-link/server /app/mmdvm-link/server

WORKDIR /app/mmdvm-link/server
CMD ["python", "-u", "server_proto.py"]

