from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import count
from typing import Any, Never, Self


@dataclass(frozen=True)
class _ReaderFailure:
    error: Exception


class OmpRpcClient:
    """Synchronous client for one persistent ``omp --mode rpc`` process."""

    def __init__(self, command: Sequence[str], timeout: float = 1_800) -> None:
        self._command = list(command)
        self._timeout = timeout
        self._ids = count(1)
        self._frames: queue.Queue[dict[str, Any] | _ReaderFailure] = queue.Queue()
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None
        self._start()

    def _start(self) -> None:
        process = subprocess.Popen(
            self._command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._process = process
        self._reader = threading.Thread(target=self._read_frames, daemon=True)
        self._reader.start()
        ready = self._receive(time.monotonic() + self._timeout)
        if ready.get("type") != "ready":
            self.close()
            raise RuntimeError(f"OMP RPC did not emit a ready frame: {ready!r}")

    def _read_frames(self) -> None:
        process = self._require_process()
        assert process.stdout is not None
        try:
            for line in process.stdout:
                if line.strip():
                    self._frames.put(json.loads(line))
        except (json.JSONDecodeError, OSError, UnicodeError) as error:
            self._frames.put(_ReaderFailure(error))
        finally:
            self._frames.put(_ReaderFailure(RuntimeError("OMP RPC process closed its output")))

    def _require_process(self) -> subprocess.Popen[str]:
        if self._process is None:
            raise RuntimeError("OMP RPC client is closed")
        return self._process

    def _send(self, payload: dict[str, Any]) -> None:
        process = self._require_process()
        if process.poll() is not None:
            raise RuntimeError(f"OMP RPC exited with status {process.returncode}")
        assert process.stdin is not None
        process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
        process.stdin.flush()

    @staticmethod
    def _raise_reader_failure(failure: _ReaderFailure) -> Never:
        raise RuntimeError("OMP RPC reader failed") from failure.error

    def _receive(self, deadline: float) -> dict[str, Any]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Timed out waiting for OMP RPC")
        try:
            frame = self._frames.get(timeout=remaining)
        except queue.Empty as error:
            raise TimeoutError("Timed out waiting for OMP RPC") from error
        if isinstance(frame, _ReaderFailure):
            self._raise_reader_failure(frame)
        return frame

    def _request(self, command: str, **fields: Any) -> Any:
        request_id = f"req-{next(self._ids)}"
        self._send({"id": request_id, "type": command, **fields})
        deadline = time.monotonic() + self._timeout
        while True:
            frame = self._receive(deadline)
            if frame.get("type") != "response" or frame.get("id") != request_id:
                self._handle_ui_request(frame)
                continue
            if not frame.get("success"):
                raise RuntimeError(str(frame.get("error", f"OMP RPC {command} failed")))
            return frame.get("data")

    def _handle_ui_request(self, frame: dict[str, Any]) -> None:
        if frame.get("type") == "extension_ui_request" and frame.get("id"):
            self._send(
                {
                    "type": "extension_ui_response",
                    "id": frame["id"],
                    "cancelled": True,
                }
            )

    def run(self, prompt: str) -> str:
        """Start a fresh OMP session, run one prompt, and return its final text."""
        with self._lock:
            self._request("new_session")
            request_id = f"req-{next(self._ids)}"
            self._send({"id": request_id, "type": "prompt", "message": prompt})
            deadline = time.monotonic() + self._timeout
            acknowledged = False
            terminal = False

            while not (acknowledged and terminal):
                frame = self._receive(deadline)
                self._handle_ui_request(frame)
                if frame.get("type") == "response" and frame.get("id") == request_id:
                    if not frame.get("success"):
                        raise RuntimeError(str(frame.get("error", "OMP prompt failed")))
                    acknowledged = True
                    data = frame.get("data") or {}
                    if data.get("agentInvoked") is False:
                        terminal = True
                elif frame.get("type") == "agent_end" and frame.get("isTerminal") is not False:
                    terminal = True

            data = self._request("get_last_assistant_text")
            if isinstance(data, str):
                return data
            if isinstance(data, dict):
                for key in ("text", "message", "output"):
                    value = data.get(key)
                    if isinstance(value, str):
                        return value
            return ""

    def close(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        if process.stdin is not None:
            process.stdin.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if process.stdout is not None:
            process.stdout.close()
        if self._reader is not None:
            self._reader.join(timeout=5)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
