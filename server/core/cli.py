"""
CLI menu: Generate Installer, List Active Nodes, Monitor Node, Send Command.
"""
from __future__ import annotations

import threading
from pathlib import Path
from queue import Empty, Queue
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .mqtt_handler import MQTTHandler
    from .state import State


def run(
    state: State,
    mqtt_handler: MQTTHandler,
    *,
    output_dir: str,
    server_addr: str,
    broker_password_file: str | None,
) -> None:
    from .installer_gen import generate as installer_generate
    from .installer_gen import InstallerGenError

    def do_generate() -> None:
        if not broker_password_file or not broker_password_file.strip():
            print("Missing BROKER_PASSWORD_FILE. Set it in server/.env before generating installer.")
            return
        try:
            path = installer_generate(state, Path(output_dir), server_addr, broker_password_file)
        except InstallerGenError as e:
            print(str(e))
            return
        print(f"Generated: {path}")

    while True:
        print()
        print("1. Generate New Client Installer")
        print("2. List Active Nodes")
        print("3. Monitor Node")
        print("4. Send Command")
        print("0. Exit")
        try:
            choice = input("Choice: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if choice == "0":
            break
        if choice == "1":
            do_generate()
            continue
        if choice == "2":
            nodes = state.get_active_nodes()
            if not nodes:
                print("No active nodes.")
            else:
                for node_id in nodes:
                    print(f"{node_id}\tonline")
            continue
        if choice == "3":
            node_id = input("Node ID: ").strip()
            if not node_id:
                continue
            if not state.has_node(node_id):
                print("Unknown or unbound node.")
                continue
            for line, ts in state.get_telemetry_snapshot(node_id):
                print(f"[{ts}] {line}")
            q: Queue[tuple[str, str]] = Queue()
            state.register_telemetry_listener(node_id, q)
            stop = threading.Event()

            def wait_enter() -> None:
                try:
                    input()
                except (EOFError, KeyboardInterrupt):
                    pass
                stop.set()

            t = threading.Thread(target=wait_enter, daemon=True)
            t.start()
            print("Monitoring (press Enter to stop)...")
            try:
                while not stop.wait(timeout=0.3):
                    try:
                        while True:
                            line, ts = q.get_nowait()
                            print(f"[{ts}] {line}")
                    except Empty:
                        pass
            except (EOFError, KeyboardInterrupt):
                stop.set()
            finally:
                state.unregister_telemetry_listener(node_id, q)
            continue
        if choice == "4":
            node_id = input("Node ID: ").strip()
            if not node_id:
                continue
            if not state.has_node(node_id):
                print("Unknown or unbound node.")
                continue
            cmd = input("Command: ").strip()
            if not cmd:
                continue
            mqtt_handler.publish_cmd(node_id, cmd)
            print("Command sent.")
            continue
        print("Invalid choice.")
