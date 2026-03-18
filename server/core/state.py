"""
Thread-safe in-memory state for the Central Controller.
Optional JSON persist for bindings so they survive restart.
"""
from __future__ import annotations

import hashlib
import json
import threading
from collections import deque
from pathlib import Path
from queue import Queue
from typing import Optional

# Per-node telemetry buffer size
TELEMETRY_MAX_LINES = 100


class State:
    def __init__(self, bindings_path: Optional[str] = None) -> None:
        self._lock = threading.Lock()
        # node_id -> token_fingerprint (issued at gen-client)
        self.issued: dict[str, str] = {}
        # token_fingerprint -> hardware_serial (after bind)
        self.hardware_bindings: dict[str, str] = {}
        # node_id -> "online" | "offline" | "unknown"
        self.status: dict[str, str] = {}
        # node_id -> deque of (log_line, timestamp)
        self.telemetry: dict[str, deque[tuple[str, str]]] = {}
        # Optional: queues registered for "monitor" to receive new lines
        self._telemetry_listeners: dict[str, list[Queue[tuple[str, str]]]] = {}
        self._bindings_path = Path(bindings_path) if bindings_path else None
        if self._bindings_path and self._bindings_path.exists():
            self._load_bindings()

    @staticmethod
    def _token_fingerprint(one_time_token: str) -> str:
        # Non-reversible; avoids persisting plaintext tokens while keeping binding correctness.
        return hashlib.sha256(one_time_token.encode("utf-8")).hexdigest()

    def _load_bindings(self) -> None:
        try:
            data = json.loads(self._bindings_path.read_text(encoding="utf-8"))
            # Backward compatible load + migrate:
            # - old format: hardware_bindings {token: serial}, issued [{node_id, token}]
            # - new format: hardware_bindings {token_fp: serial}, issued [{node_id, token_fp}]
            hw_raw = data.get("hardware_bindings", {}) or {}
            migrated_hw: dict[str, str] = {}
            needs_save = False
            if isinstance(hw_raw, dict):
                for k, v in hw_raw.items():
                    if not isinstance(k, str) or v is None:
                        continue
                    is_fp = len(k) == 64 and all(c in "0123456789abcdef" for c in k)
                    token_fp = k if is_fp else self._token_fingerprint(k)
                    if not is_fp:
                        needs_save = True
                    migrated_hw[token_fp] = str(v)
            self.hardware_bindings = migrated_hw

            issued_list = data.get("issued", []) or []
            migrated_issued: dict[str, str] = {}
            if isinstance(issued_list, list):
                for item in issued_list:
                    if not isinstance(item, dict) or "node_id" not in item:
                        continue
                    node_id = str(item["node_id"])
                    token_fp = item.get("token_fp")
                    if isinstance(token_fp, str) and len(token_fp) == 64 and all(c in "0123456789abcdef" for c in token_fp):
                        migrated_issued[node_id] = token_fp
                        continue
                    token = item.get("token")
                    if isinstance(token, str) and token:
                        migrated_issued[node_id] = self._token_fingerprint(token)
                        needs_save = True
            self.issued = migrated_issued

            # If we had to migrate, persist the safer format.
            if needs_save:
                self._save_bindings()
        except (OSError, json.JSONDecodeError):
            pass

    def _save_bindings(self) -> None:
        if not self._bindings_path:
            return
        try:
            issued_list = [
                {"node_id": n, "token_fp": t} for n, t in self.issued.items()
            ]
            self._bindings_path.write_text(
                json.dumps(
                    {
                        "hardware_bindings": self.hardware_bindings,
                        "issued": issued_list,
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    def add_issued(self, node_id: str, token: str) -> None:
        with self._lock:
            self.issued[node_id] = self._token_fingerprint(token)
            self._save_bindings()

    def remove_issued(self, node_id: str) -> None:
        """Remove node_id from issued and from hardware_bindings if present. Calls _save_bindings."""
        with self._lock:
            token_fp = self.issued.pop(node_id, None)
            if token_fp and token_fp in self.hardware_bindings:
                del self.hardware_bindings[token_fp]
            self._save_bindings()

    def _is_bound(self, node_id: str) -> bool:
        token_fp = self.issued.get(node_id)
        if not token_fp:
            return False
        return token_fp in self.hardware_bindings

    def try_bind(self, node_id: str, one_time_token: str, hardware_serial: str) -> bool:
        """Bind token to hardware_serial. Returns True if bound (or idempotent same serial)."""
        with self._lock:
            token_fp = self._token_fingerprint(one_time_token)
            if self.issued.get(node_id) != token_fp:
                return False
            existing = self.hardware_bindings.get(token_fp)
            if existing is None:
                self.hardware_bindings[token_fp] = hardware_serial
                self._save_bindings()
                return True
            if existing == hardware_serial:
                return True  # idempotent
            return False  # different hardware, reject

    def append_telemetry(self, node_id: str, log_line: str, timestamp: str) -> None:
        with self._lock:
            if node_id not in self.telemetry:
                self.telemetry[node_id] = deque(maxlen=TELEMETRY_MAX_LINES)
            d = self.telemetry[node_id]
            d.append((log_line, timestamp))
            for q in self._telemetry_listeners.get(node_id, []):
                try:
                    q.put_nowait((log_line, timestamp))
                except Exception:
                    pass

    def set_status(self, node_id: str, status: str) -> None:
        allowed = {"online", "offline", "unknown"}
        if status not in allowed:
            status = "unknown"
        with self._lock:
            self.status[node_id] = status

    def get_active_nodes(self) -> list[str]:
        """Return sorted list of bound node_ids whose last status is 'online'."""
        with self._lock:
            active = [
                nid
                for nid in self.status
                if self.status[nid] == "online" and self._is_bound(nid)
            ]
            return sorted(active)

    def get_bound_nodes(self) -> list[str]:
        """Return sorted list of all bound node_ids (for List Nodes and Send Command)."""
        with self._lock:
            bound = [nid for nid in self.issued if self._is_bound(nid)]
            return sorted(bound)

    def get_bound_nodes_status(self) -> list[tuple[str, str]]:
        """Return sorted list of (node_id, status) for bound nodes only."""
        with self._lock:
            bound = [nid for nid in self.issued if self._is_bound(nid)]
            bound_sorted = sorted(bound)
            return [(nid, self.status.get(nid, "unknown")) for nid in bound_sorted]

    def has_node(self, node_id: str) -> bool:
        with self._lock:
            return self._is_bound(node_id)

    def get_telemetry_snapshot(self, node_id: str) -> list[tuple[str, str]]:
        with self._lock:
            return list(self.telemetry.get(node_id, deque()))

    def register_telemetry_listener(
        self, node_id: str, queue: Queue[tuple[str, str]]
    ) -> None:
        with self._lock:
            if node_id not in self._telemetry_listeners:
                self._telemetry_listeners[node_id] = []
            self._telemetry_listeners[node_id].append(queue)

    def unregister_telemetry_listener(
        self, node_id: str, queue: Queue[tuple[str, str]]
    ) -> None:
        with self._lock:
            lst = self._telemetry_listeners.get(node_id, [])
            if queue in lst:
                lst.remove(queue)
