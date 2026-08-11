"""Headless coding-host adapters."""

import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
from typing import Iterable

from sunday.adapters.base import HostAdapter, ModelExecution, VerificationStatus
from sunday.routing import MODEL_POOLS, Route


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


def _codex_rollout_model(output: str) -> tuple[str | None, str | None]:
    thread_id = None
    for value in _json_values(output):
        if isinstance(value, dict) and value.get("type") == "thread.started":
            thread_id = value.get("thread_id")
    if not thread_id:
        return None, None
    root = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    sessions = root / "sessions"
    if not sessions.is_dir():
        return None, None
    matches = sorted(
        sessions.rglob(f"rollout-*{thread_id}.jsonl"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in matches:
        try:
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    value = json.loads(line)
                    if value.get("type") != "turn_context":
                        continue
                    model = value.get("payload", {}).get("model")
                    if isinstance(model, str) and model:
                        return model, str(path)
        except (OSError, json.JSONDecodeError):
            continue
    return None, None


class CommandHostAdapter(HostAdapter):
    def __init__(self, name: str, timeout: int = 3600):
        self.name = name
        self.timeout = timeout
        self.process: subprocess.Popen | None = None

    def capabilities(self) -> dict:
        executable = self._executable()
        capabilities = {
            "host": self.name,
            "available": bool(shutil.which(executable)),
            "executable": shutil.which(executable),
            "headless": True,
            "explicit_model": True,
            "structured_output": self.name in {"codex", "claude", "gemini"},
        }
        if self.name == "antigravity" and executable == "gemini":
            capabilities["fallback"] = "gemini"
        return capabilities

    def discover_models(self) -> list[str]:
        return list(dict.fromkeys(
            candidate.model
            for candidates in MODEL_POOLS.get(self.name, {}).values()
            for candidate in candidates
        ))

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
            command = [part.format(**values) for part in shlex.split(override)]
            # Commands ending in -p/--print expect the prompt as the next
            # argument. Other override templates keep the stdin contract.
            return command, not bool(command and command[-1] in {"-p", "--print"})
        if self.name == "codex":
            command = [
                "codex", "exec", "--json", "--ignore-user-config",
                "--skip-git-repo-check", "--model", route.model,
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
            return [
                "gemini", "--model", route.model, "--output-format", "json",
                "--sandbox", "--approval-mode", "plan" if read_only else "yolo",
            ], True
        executable = self._executable()
        if executable == "gemini":
            return [
                "gemini", "--model", route.model, "--output-format", "json",
                "--sandbox", "--approval-mode", "plan" if read_only else "yolo",
            ], True
        command = [executable, "--model", route.model]
        if not read_only:
            command.append("--dangerously-skip-permissions")
        # Antigravity's documented headless interface accepts the prompt as the
        # value of -p. It does not expose Codex-style --mode/--prompt flags.
        command.append("-p")
        return command, False

    def probe_model(self, model: str, repository: Path | None = None) -> ModelExecution:
        if repository is None:
            with tempfile.TemporaryDirectory(prefix="sunday-model-probe-") as temporary:
                return self._probe_model(model, Path(temporary))
        return self._probe_model(model, repository.resolve())

    def _probe_model(self, model: str, repository: Path) -> ModelExecution:
        route = Route(
            phase="diagnostics",
            host=self.name,
            agent="sunday-model-probe",
            tier="diagnostic",
            model=model,
            effort=None,
        )
        command, accepts_stdin = self._command(route, repository, True)
        if self.name == "claude" and command[0] == "claude":
            command.extend(["--tools", ""])
        prompt = (
            'Return exactly {"sunday_model_probe":"ok"}. '
            "Do not inspect files, invoke tools, or perform any other work."
        )
        return self._execute(command, accepts_stdin, prompt, repository, model)

    def execute_agent(
        self, route: Route, prompt: str, repository: Path, read_only: bool
    ) -> ModelExecution:
        command, accepts_stdin = self._command(route, repository, read_only)
        return self._execute(command, accepts_stdin, prompt, repository, route.model, raise_missing=True)

    def _execute(
        self,
        command: list[str],
        accepts_stdin: bool,
        prompt: str,
        repository: Path,
        requested_model: str,
        raise_missing: bool = False,
    ) -> ModelExecution:
        started = time.monotonic()
        executable = shutil.which(command[0])
        if not executable:
            if raise_missing:
                raise RuntimeError(f"{self.name} executable not found: {command[0]}")
            return ModelExecution(
                requested_model=requested_model,
                observed_model=None,
                verification_status="unavailable",
                verification_evidence={
                    "command": self._safe_command(command),
                    "reason": "host executable not found",
                },
                exit_code=127,
                duration=round(time.monotonic() - started, 3),
                output=f"{self.name} executable not found: {command[0]}",
            )
        try:
            process_command = [*command, prompt] if not accepts_stdin else command
            self.process = subprocess.Popen(
                process_command,
                cwd=repository,
                stdin=subprocess.PIPE if accepts_stdin else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                start_new_session=os.name != "nt",
                creationflags=(
                    subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
                ),
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
        rollout = None
        if self.name == "codex" and not observed:
            observed, rollout = _codex_rollout_model(output)
        status = self._verification_status(requested_model, observed, return_code)
        evidence = {
            "command": self._safe_command(command),
            "return_code": return_code,
            "stderr": stderr[-4000:],
            "verification_source": (
                "codex rollout turn_context" if rollout
                else "host output" if observed
                else "requested CLI option only"
            ),
        }
        if rollout:
            evidence["rollout"] = rollout
        return ModelExecution(
            requested_model=requested_model,
            observed_model=observed,
            verification_status=status,
            verification_evidence=evidence,
            exit_code=return_code,
            duration=round(time.monotonic() - started, 3),
            output=output or stderr.strip(),
            confidence=confidence,
        )

    def verify_model_used(self, route: Route, result: ModelExecution) -> bool:
        return bool(
            result.verification_status == "confirmed"
            and result.observed_model
            and self._same_model(route.model, result.observed_model)
        )

    def cancel(self) -> None:
        if self.process and self.process.poll() is None:
            process = self.process
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    check=False,
                )
            else:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                except ProcessLookupError:
                    pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        check=False,
                    )
                else:
                    try:
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    @staticmethod
    def _same_model(requested: str, observed: str) -> bool:
        requested = requested.casefold().strip()
        observed = observed.casefold().strip().rsplit("/", 1)[-1]
        if requested == "auto":
            return observed.startswith("gemini")
        if requested == observed:
            return True
        gemini_aliases = {
            "flash-lite": "flash-lite",
            "flash": "flash",
            "pro": "pro",
        }
        if requested in gemini_aliases:
            alias = gemini_aliases[requested]
            if alias == "flash" and "flash-lite" in observed:
                return False
            return alias in observed.split("-") or f"-{alias}-" in f"-{observed}-"
        prefix = f"{requested}-"
        if observed.startswith(prefix):
            snapshot = observed[len(prefix):].replace("-", "")
            return snapshot.isdigit()
        return False

    @classmethod
    def _verification_status(
        cls, requested: str, observed: str | None, exit_code: int
    ) -> VerificationStatus:
        if exit_code != 0:
            return "unavailable"
        if observed:
            return "confirmed" if cls._same_model(requested, observed) else "mismatched"
        return "requested_only"

    @staticmethod
    def _safe_command(command: list[str]) -> list[str]:
        safe: list[str] = []
        redact_next = False
        for part in command:
            lowered = part.casefold()
            sensitive = any(word in lowered for word in ("key", "token", "password", "secret"))
            if redact_next or sensitive:
                safe.append("[REDACTED]")
            else:
                safe.append(part)
            redact_next = sensitive and "=" not in part
        return safe


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
            if (
                (capabilities := (adapter := CommandHostAdapter(name)).capabilities())["available"]
                and not capabilities.get("fallback")
            )
        ]
