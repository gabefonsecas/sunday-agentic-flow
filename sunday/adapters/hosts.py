"""Headless coding-host adapters."""

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import time
from typing import Iterable

from sunday.adapters.base import ExecutionResult, HostAdapter
from sunday.routing import Route


def _models(value: object) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in {"model", "modelname", "model_name"} and isinstance(item, str):
                found.append(item)
            elif key.lower() in {"modelusage", "model_usage"} and isinstance(item, dict):
                found.extend(str(name) for name in item)
            found.extend(_models(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_models(item))
    return found


def _json_values(output: str) -> Iterable[object]:
    try:
        yield json.loads(output)
    except json.JSONDecodeError:
        pass
    for line in output.splitlines():
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


class CommandHostAdapter(HostAdapter):
    def __init__(self, name: str, timeout: int = 3600):
        self.name = name
        self.timeout = timeout
        self.process: subprocess.Popen | None = None

    def capabilities(self) -> dict:
        executable = self._executable()
        return {
            "host": self.name,
            "available": bool(shutil.which(executable)),
            "executable": shutil.which(executable),
            "headless": True,
            "explicit_model": True,
            "structured_output": self.name in {"codex", "claude", "gemini"},
        }

    def _executable(self) -> str:
        override = os.environ.get(f"SUNDAY_{self.name.upper()}_COMMAND")
        if override:
            return shlex.split(override)[0]
        if self.name == "antigravity":
            return "agy" if shutil.which("agy") else "gemini"
        return self.name

    def _command(self, route: Route, repository: Path, read_only: bool) -> tuple[list[str], bool]:
        override = os.environ.get(f"SUNDAY_{self.name.upper()}_COMMAND")
        if override:
            values = {
                "model": route.model,
                "effort": route.effort or "",
                "repository": str(repository),
                "mode": "read-only" if read_only else "workspace-write",
            }
            return [part.format(**values) for part in shlex.split(override)], True
        if self.name == "codex":
            command = [
                "codex", "exec", "--json", "--model", route.model,
                "--sandbox", "read-only" if read_only else "workspace-write",
                "--cd", str(repository), "-",
            ]
            if route.effort:
                command[2:2] = ["--config", f'model_reasoning_effort="{route.effort}"']
            return command, True
        if self.name == "claude":
            command = [
                "claude", "--print", "--output-format", "json", "--model", route.model,
                "--effort", route.effort or "high", "--permission-mode",
                "plan" if read_only else "acceptEdits",
            ]
            return command, True
        if self.name == "gemini":
            return ["gemini", "--model", route.model, "--output-format", "json"], True
        executable = self._executable()
        if executable == "gemini":
            return ["gemini", "--model", route.model, "--output-format", "json"], True
        return [executable, "--model", route.model, "--prompt", "-"], True

    def execute_agent(self, route: Route, prompt: str, repository: Path, read_only: bool) -> ExecutionResult:
        command, accepts_stdin = self._command(route, repository, read_only)
        if not shutil.which(command[0]):
            raise RuntimeError(f"{self.name} executable not found: {command[0]}")
        started = time.monotonic()
        try:
            self.process = subprocess.Popen(
                command,
                cwd=repository,
                stdin=subprocess.PIPE if accepts_stdin else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            stdout, stderr = self.process.communicate(prompt if accepts_stdin else None, timeout=self.timeout)
            return_code = self.process.returncode
        except subprocess.TimeoutExpired:
            self.cancel()
            raise TimeoutError(f"{self.name} phase timed out after {self.timeout} seconds")
        finally:
            self.process = None
        output = stdout.strip()
        observed = None
        confidence = None
        for value in _json_values(output):
            candidates = _models(value)
            if candidates:
                observed = candidates[-1]
            if isinstance(value, dict) and isinstance(value.get("confidence"), (int, float)):
                confidence = float(value["confidence"])
        verified = bool(observed and self._same_model(route.model, observed))
        if not observed and return_code == 0:
            verified = True
        evidence = {
            "command": ["[REDACTED]" if "key" in part.lower() else part for part in command[:-1]],
            "return_code": return_code,
            "stderr": stderr[-4000:],
            "verification_source": "host output" if observed else "explicit CLI selection",
        }
        return ExecutionResult(
            success=return_code == 0,
            output=output or stderr.strip(),
            requested_model=route.model,
            observed_model=observed,
            model_verified=verified,
            duration_seconds=round(time.monotonic() - started, 3),
            confidence=confidence,
            evidence=evidence,
        )

    def verify_model_used(self, route: Route, result: ExecutionResult) -> bool:
        if not result.model_verified:
            return False
        if not result.observed_model:
            return (result.evidence or {}).get("verification_source") == "explicit CLI selection"
        return self._same_model(route.model, result.observed_model)

    def cancel(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()

    @staticmethod
    def _same_model(requested: str, observed: str) -> bool:
        requested = requested.casefold()
        observed = observed.casefold()
        if requested == "auto":
            return observed.startswith("gemini")
        return requested == observed or requested in observed or observed in requested


class HostRegistry:
    ORDER = ("codex", "claude", "gemini", "antigravity")

    def detect(self, preferred: str = "auto") -> CommandHostAdapter:
        names = self.ORDER if preferred == "auto" else (preferred,)
        for name in names:
            adapter = CommandHostAdapter(name)
            if adapter.capabilities()["available"]:
                return adapter
        raise RuntimeError(f"No supported host available for selection: {preferred}")

    def alternatives(self, current: str) -> list[CommandHostAdapter]:
        return [
            adapter for name in self.ORDER if name != current
            if (adapter := CommandHostAdapter(name)).capabilities()["available"]
        ]
