# AGENTS.md

Canonical instructions for AI coding agents working in this repository. Keep this file short; deeper docs are linked below.

## Purpose

`mmdvm-link` is a proof of concept with two parts:

- **Server / CLI** (`server/`): a central controller that talks to a Mosquitto MQTT broker. It issues node installers, binds nodes, shows telemetry, and sends commands from an interactive CLI.
- **Edge agent** (`client/`): runs on a Pi-Star device, connects to the broker over TLS, registers, publishes status and log telemetry, and executes commands.

It is part of the `trac-portal` program. The orchestration root is the `trac-portal` repository; this directory is a git submodule with its own GitHub repository.

## Stack

- Python 3.11+ (CI and the server Docker image use 3.15; the Pi-Star client must run on 3.11+)
- Runtime dependencies (`requirements.txt`): `paho-mqtt>=2.1.0`, `python-dotenv>=1.0.1`
- Dev tooling (`requirements-dev.txt`): `ruff` (lint and format; config in `pyproject.toml`)
- Mosquitto MQTT broker (external to this repo's Python code; deployed by the root repo)
- Target platform for the client: Pi-Star (Raspberry Pi, Debian-based)

## Setup and run

```bash
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
```

Configuration is read from environment variables, optionally loaded from `.env` files:

- Server: `cp server/.env.example server/.env`, then fill in `MQTT_BROKER`, `MQTT_USER`, `MQTT_PASSWORD`, `SERVER_ADDR` (required) and optional values.
- Client: `cp client/.env.example client/.env` (on Pi-Star the file is `/opt/mmdvm_link/.env`). The client parses its `.env` itself and lets real environment variables win.

Run:

```bash
python -u server/server_proto.py
python -u client/client_proto.py
```

## Verify

```bash
python scripts/verify.py
```

This is the single definition of "done". It runs `ruff check .`, `ruff format --check .`, and `python -m compileall -q server client`, and exits non-zero on any failure. CI runs the same command in the `verify` job of `.github/workflows/docker-ghrc.yaml`. Run it before you report a task as complete.

## Structure

- `server/server_proto.py`: server entry point; loads `server/.env`, starts the MQTT handler and the CLI.
- `server/core/`: `state.py` (thread-safe in-memory state, optional bindings persistence), `mqtt_handler.py` (broker subscriptions), `cli.py` (interactive menu), `installer_gen.py` (generates the client installer script).
- `client/client_proto.py`: client entry point; reads config, validates `NODE_ID`, starts the agent.
- `client/agents/pistar/`: Pi-Star agent (`agent.py`, `config.py`, `install.sh`).
- `client/core/`: `mqtt_client.py` (paho wrapper, topics, LWT), `identity.py` (node identity helpers).
- `docker/server.Dockerfile`: server image (copies `requirements.txt` and `server/`).
- `scripts/verify.py`: verification entry point.
- `docs/conventions/python.md`: Python conventions (style, layout, config, logging).
- `README.md`: human-facing setup notes (Turkish).

## MQTT architecture

Mosquitto runs with two listeners:

- **Internal** (`1883`): no auth, no ACL. Only the server connects here, over the container network. Never published to the host.
- **External** (`8883`): TLS, username/password, and ACL are mandatory. Clients connect here.

Topics in use: `nodes/register`, `nodes/register/ack/{node_id}`, `nodes/bind`, `nodes/status/{node_id}`, `nodes/telemetry/{node_id}`, `nodes/cmd/{node_id}`. The broker ACL must let each client use only its own `node_id` topics.

## Deployment

Deployment artifacts (compose file, Mosquitto config, `update.sh`) live in the root `trac-portal` repository under `server/mmdvm-link`. Agents do not deploy anything. Image builds are done by CI in this repo; images are pushed to GHCR only on `main` and tags.

## Testing policy

> Tests are expensive; keep them to a minimum. Do not add tests by default and never add "write tests" as a routine acceptance criterion. Add a test only when it rests on a solid reason: authentication/authorization, data integrity or irreversible operations, non-trivial pure logic (parsing, date/time, state machines), or a production bug likely to recur. State that reason in one sentence in the PR description. End-to-end tests and any new test framework/infrastructure require explicit approval from the project owner. Do not write tests for trivial CRUD, getters, rendering/snapshots, or mock-heavy controller code. Existing tests stay and must pass.

This repository currently has no test suite. Do not introduce one without the approval described above.

## Git and PR workflow

- `main` is protected. Work on a task branch (for example `chore/<topic>` or `fix/<topic>`) and open a pull request against `main`.
- Use conventional commit messages (`feat:`, `fix:`, `chore:`, `style:`, `docs:`) and reference the issue number in the title, for example `chore: make the repo agent-ready (#123)`.
- Issues live in the root repository `TRAC-Erzurum/trac-portal`. Close them from the PR body with `Closes TRAC-Erzurum/trac-portal#<n>`.
- Fill in `.github/pull_request_template.md`, including the verify output summary.
- Keep each PR to one concern. Do not mix formatting churn with behaviour changes.
- After this repository's PR merges, the root repository gets a follow-up PR that bumps the submodule pointer.

## Conventions

- Python style, module layout, configuration, and logging: `docs/conventions/python.md`.
- Keep behaviour unchanged in refactors. Do not change MQTT topics, payload contracts, or environment variable names without an explicit task for it.
- Dependency upgrades are separate tasks; do not bump versions as a side effect.

## Boundaries

- Never push to `main`, never force-push, never bypass branch protection or use administrative merge options.
- Never deploy, and never touch the production server or the production broker.
- Never run migrations, seeds, or destructive commands against any database.
- Never read, print, or commit `.env` files, secrets, tokens, passwords, or certificates (`*.pem`).
- Never commit generated or host-specific files: `server/bindings.json`, `server/install_*.sh`, `.env`, `*.pem`.
- Stop and report when the task needs changes outside its scope.
