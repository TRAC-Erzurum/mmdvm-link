FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# mosquitto_passwd is required by server/core/installer_gen.py
RUN apt-get update \
    && apt-get install -y --no-install-recommends mosquitto \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY server /app/server

WORKDIR /app/server
CMD ["python", "-u", "server_proto.py"]

