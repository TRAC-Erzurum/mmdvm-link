# MMDVM-Link

Merkezi yönetim (server/CLI) ve edge cihaz ajanı (client, Pi-Star) için PoC.

Ana repo (deploy/compose/CI): `trac-portal`.

## Yapı

- **`server/`** — Merkezi yönetim (MQTT + CLI). Giriş: `server/server_proto.py`
- **`client/`** — Edge cihaz ajanları (Pi-Star). Giriş: `client/client_proto.py`
- **`docker/`** — Deploy artefact’ları (server Dockerfile, Mosquitto entrypoint)

## MQTT mimarisi (PoC)

Tek Mosquitto container içinde 2 listener:

- **Internal (container network)**: `1883` — auth/ACL yok (server buradan bağlanır). Host’a publish edilmez.
- **External (internet)**: `8883` — TLS + password + ACL zorunlu (client buradan bağlanır).

## Gereksinimler (lokal)

- Python 3.11+ (PoC)
- `pip install -r requirements.txt`

## Kurulum (lokal çalıştırma)

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

### Server env

Server `.env` dosyası: `server/.env.example` → `server/.env`

| Değişken | Açıklama |
|----------|----------|
| `MQTT_BROKER` | Broker host (compose içinde genelde `mosquitto`) |
| `MQTT_PORT` | Internal listener port (PoC: `1883`) |
| `SERVER_ADDR` | Client’ların erişeceği broker adresi (örn. `${DOMAIN}:8883`) |
| `BROKER_PASSWORD_FILE` | Mosquitto passwd dosyası path’i (örn. `/mosquitto/config/passwd`) |
| `BINDINGS_FILE` | (Opsiyonel) server bindings persist dosyası |
| `MQTT_TLS` / `MQTT_TLS_CA` / `MQTT_TLS_INSECURE` | (Opsiyonel) TLS ayarları; internal 1883 için kapalı olmalı |

### Client env

Client `.env` dosyası (Pi-Star hedefi): `/opt/mmdvm_link/.env`

| Değişken | Açıklama |
|----------|----------|
| `NODE_ID` | Node kimliği (username) |
| `NODE_TOKEN` | Node şifresi (server’ın installer ile ürettiği token) |
| `SERVER_ADDR` | Broker external adresi (`host:8883`) |
| `MQTT_TLS` | `1` (external TLS) |
| `MQTT_TLS_CA` | (Opsiyonel) custom CA path |
| `MQTT_TLS_INSECURE` | (Opsiyonel) `1` ise cert doğrulaması kapatılır (önerilmez) |

## Komutlar

```bash
python -u server/server_proto.py
python -u client/client_proto.py
```

## Deploy (trac-portal)

- Root `docker-compose.yml` Mosquitto’yu ve `mmdvm-link-server` (profile `poc`) servisini içerir.
- `update.sh` deploy sırasında gerekli image’ları pull eder ve Mosquitto’yu ayağa kaldırır.

## CI/CD (mmdvm-link-server image)

- PR: build/validation (push yok)
- main push: `pre-release` + `main-build.N` push
- tag `v*`: `pre-release` → `vX.Y.Z` + `latest` promote
- root deploy workflow: `mmdvm_link_server_version=latest` ise en son `v*` tag’i deploy eder
