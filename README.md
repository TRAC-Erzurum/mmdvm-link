# mmdvm-link

Merkezi sunucu ve edge cihaz (Pi-Star vb.) katmanları için PoC.

## Yapı

- **server/** — Merkezi yönetim (MQTT, CLI). Giriş: `server_proto.py`
- **client/** — Edge cihaz ajanları (pistar, generic). Giriş: `client_proto.py`
- **docs/** — Kontrat ve PoC dokümantasyonu

## Kurulum

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

Server için: `server/.env.example` → `server/.env` kopyalayıp `SECRET_TOKEN` ve `MQTT_BROKER` doldur.
