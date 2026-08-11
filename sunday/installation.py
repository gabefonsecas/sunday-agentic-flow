"""Transactional, release-based installation lifecycle for Sunday."""

from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import threading
from tempfile import TemporaryDirectory, mkdtemp
import urllib.request
import uuid
import venv
import zipfile

from sunday import __version__
from sunday.config import DEFAULT_CONFIG
from sunday.paths import bin_dir, config_dir, installation_dir, releases_dir
from sunday.security import load_env

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_NAME = "sunday-agentic-flow"
GITHUB_REPOSITORY = "gabefonsecas/sunday-agentic-flow"
GITHUB_API = "https://api.github.com"
MAX_DOWNLOAD_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
COPY_IGNORE = shutil.ignore_patterns(
    ".git", ".env", ".venv", "__pycache__", "*.pyc", "*.egg-info", "build", "dist"
)
_INSTALL_THREAD_LOCK = threading.RLock()
_INSTALL_LOCK_STATE = threading.local()


@contextmanager
def _installation_lock():
    """Serialize installation mutations across threads and processes."""
    with _INSTALL_THREAD_LOCK:
        depth = getattr(_INSTALL_LOCK_STATE, "depth", 0)
        if depth:
            _INSTALL_LOCK_STATE.depth = depth + 1
            try:
                yield
            finally:
                _INSTALL_LOCK_STATE.depth -= 1
            return
        installation_dir().mkdir(parents=True, exist_ok=True)
        path = installation_dir() / ".installation.lock"
        with path.open("a+b") as handle:
            handle.seek(0)
            if handle.tell() == 0 and path.stat().st_size == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            _INSTALL_LOCK_STATE.depth = 1
            try:
                yield
            finally:
                _INSTALL_LOCK_STATE.depth = 0
                handle.seek(0)
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _serialized_installation(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with _installation_lock():
            return function(*args, **kwargs)
    return wrapped


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _remove_tree(path: Path) -> None:
    def writable(function, target, error):
        del error
        os.chmod(target, stat.S_IWRITE)
        function(target)

    shutil.rmtree(path, onerror=writable)


def _hash(path: Path) -> str | None:
    if not path.is_file() or path.is_symlink():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def transaction():
    backups: list[tuple[Path, Path | None]] = []
    with TemporaryDirectory(prefix="sunday-install-") as temp:
        directory = Path(temp)

        def prepare(target: Path) -> None:
            if any(item[0] == target for item in backups):
                return
            if target.exists() or target.is_symlink():
                backup = directory / str(len(backups))
                if target.is_symlink():
                    backup.symlink_to(os.readlink(target))
                elif target.is_dir():
                    shutil.copytree(target, backup)
                else:
                    shutil.copy2(target, backup)
                backups.append((target, backup))
            else:
                backups.append((target, None))

        try:
            yield prepare
        except Exception:
            for target, backup in reversed(backups):
                if target.is_dir() and not target.is_symlink():
                    _remove_tree(target)
                elif target.exists() or target.is_symlink():
                    target.unlink()
                if backup:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if backup.is_symlink():
                        target.symlink_to(os.readlink(backup))
                    elif backup.is_dir():
                        shutil.copytree(backup, target)
                    else:
                        shutil.copy2(backup, target)
            raise


def _copy(source: Path, target: Path, prepare) -> None:
    prepare(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_dir() and not target.is_symlink():
        _remove_tree(target)
    elif target.exists() or target.is_symlink():
        target.unlink()
    shutil.copy2(source, target)


def _link(source: Path, target: Path, prepare) -> None:
    prepare(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_dir() and not target.is_symlink():
        _remove_tree(target)
    elif target.exists() or target.is_symlink():
        target.unlink()
    if os.name == "nt":
        shutil.copytree(source, target, ignore=COPY_IGNORE)
    else:
        target.symlink_to(source, target_is_directory=True)


def _bootstrap(prepare) -> tuple[Path, Path]:
    target = installation_dir() / "run-active.py"
    prepare(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    content = f"""#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

active = json.loads(Path({str(_active_path())!r}).read_text(encoding="utf-8"))
release = Path(active["release"])
runtime = Path(active["runtime"])
if not runtime.is_absolute():
    runtime = release / runtime
script = sys.argv[1]
if script not in {{"sunday.py", "friday_mcp_proxy.py"}}:
    raise SystemExit("Invalid Sunday entrypoint")
os.execv(str(runtime), [str(runtime), str(release / "scripts" / script), *sys.argv[2:]])
"""
    target.write_text(content, encoding="utf-8", newline="")
    python = Path(getattr(sys, "_base_executable", None) or sys.executable)
    return target, python


def _launcher(name: str, script: str, bootstrap: Path, python: Path, prepare) -> Path:
    target = bin_dir() / (f"{name}.cmd" if os.name == "nt" else name)
    prepare(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        content = f'@echo off\r\n"{python}" "{bootstrap}" "{script}" %*\r\n'
    else:
        content = f'#!/bin/sh\nexec "{python}" "{bootstrap}" "{script}" "$@"\n'
    target.write_text(content, encoding="utf-8", newline="")
    if os.name != "nt":
        target.chmod(target.stat().st_mode | stat.S_IXUSR)
    return target


def _marketplace(prepare) -> Path:
    path = Path.home() / ".agents" / "plugins" / "marketplace.json"
    prepare(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.exists()
        else {
            "name": "personal",
            "interface": {"displayName": "Personal"},
            "plugins": [],
        }
    )
    entry = {
        "name": PLUGIN_NAME,
        "source": {"source": "local", "path": f"./plugins/{PLUGIN_NAME}"},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        "category": "Developer Tools",
    }
    data["plugins"] = [
        item
        for item in data.setdefault("plugins", [])
        if item.get("name") != PLUGIN_NAME
    ]
    data["plugins"].append(entry)
    _atomic_json(path, data)
    return path


def _active_path() -> Path:
    return installation_dir() / "active-release.json"


def _release_manifest_path(release: Path) -> Path:
    return release / "release-manifest.json"


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Invalid Sunday manifest: {path}") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"Invalid Sunday manifest: {path}")
    return value


def _safe_version(value: str) -> str:
    version = value.removeprefix("v")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", version):
        raise RuntimeError(f"Invalid Sunday release version: {value}")
    return version


def _source_version(source: Path, requested: str | None = None) -> str:
    version_file = source / "VERSION"
    discovered = (
        version_file.read_text(encoding="utf-8").strip()
        if version_file.is_file()
        else ""
    )
    version = _safe_version(requested or discovered or __version__)
    if requested and discovered and _safe_version(discovered) != version:
        raise RuntimeError(
            f"Release version {requested} does not match archive version {discovered}"
        )
    return version


def _venv_python(directory: Path) -> Path:
    return directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _smoke_test(release: Path, python: Path) -> None:
    result = subprocess.run(
        [str(python), str(release / "scripts" / "sunday.py"), "--help"],
        cwd=release,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise RuntimeError(f"Sunday release smoke test failed: {detail}")


def _prepare_runtime(release: Path, isolated: bool) -> tuple[str, bool, str | None]:
    if isolated:
        runtime = release / ".venv"
        try:
            venv.EnvBuilder(with_pip=False, clear=True).create(runtime)
            python = _venv_python(runtime)
            _smoke_test(release, python)
            return str(python.relative_to(release)), True, None
        except (OSError, subprocess.SubprocessError, RuntimeError) as error:
            if runtime.exists():
                _remove_tree(runtime)
            fallback_reason = str(error)
    else:
        fallback_reason = "isolated runtime disabled"
    _smoke_test(release, Path(sys.executable))
    return sys.executable, False, fallback_reason


def _runtime_path(release: Path, manifest: dict) -> Path:
    value = Path(str(manifest.get("runtime", sys.executable)))
    return release / value if not value.is_absolute() else value


def _release_manifest(
    release: Path,
    version: str,
    runtime: str,
    isolated: bool,
    source: str,
    archive_sha256: str | None,
    fallback_reason: str | None,
) -> dict:
    return {
        "schema_version": 1,
        "plugin": PLUGIN_NAME,
        "version": version,
        "release": str(release),
        "source": source,
        "archive_sha256": archive_sha256,
        "installed_at": _now(),
        "runtime": runtime,
        "runtime_isolated": isolated,
        "runtime_fallback_reason": fallback_reason,
        "smoke_test": "passed",
    }


def _initialize_configuration(prepare) -> None:
    config_dir().mkdir(parents=True, exist_ok=True)
    env = config_dir() / ".env"
    if not env.exists():
        _copy(ROOT / ".env.example", env, prepare)
        if os.name != "nt":
            env.chmod(0o600)
    config = config_dir() / "config.toml"
    if not config.exists():
        prepare(config)
        config.write_text(DEFAULT_CONFIG, encoding="utf-8")


def _activation_record(release: Path, manifest: dict) -> dict:
    active_path = _active_path()
    old = _read_json(active_path) if active_path.is_file() else {}
    history = [
        item
        for item in old.get("history", [])
        if isinstance(item, dict) and item.get("release") != str(release)
    ]
    if old.get("release") and old.get("release") != str(release):
        history.insert(
            0,
            {
                "version": old.get("version"),
                "release": old.get("release"),
                "runtime": old.get("runtime"),
            },
        )
    return {
        "schema_version": 1,
        "version": manifest["version"],
        "release": str(release),
        "runtime": manifest["runtime"],
        "activated_at": _now(),
        "history": history[:10],
    }


def _activate_release(release: Path, manifest: dict) -> dict:
    runtime = _runtime_path(release, manifest)
    if not runtime.is_file():
        raise RuntimeError(f"Sunday runtime not found: {runtime}")
    installed: list[Path] = []
    agents: dict[str, list[str]] = {}
    active = _activation_record(release, manifest)
    with transaction() as prepare:
        _initialize_configuration(prepare)
        bootstrap, bootstrap_python = _bootstrap(prepare)
        installed.append(bootstrap)
        installed.extend(
            [
                _launcher("sunday", "sunday.py", bootstrap, bootstrap_python, prepare),
                _launcher(
                    "sunday-friday-mcp",
                    "friday_mcp_proxy.py",
                    bootstrap,
                    bootstrap_python,
                    prepare,
                ),
            ]
        )
        plugin_source = Path.home() / ".agents" / "plugins" / "plugins" / PLUGIN_NAME
        _link(release, plugin_source, prepare)
        installed.append(plugin_source)
        antigravity = Path.home() / ".gemini" / "config" / "plugins" / PLUGIN_NAME
        _link(release, antigravity, prepare)
        installed.append(antigravity)
        targets = {
            "codex": Path.home() / ".codex" / "agents",
            "claude": Path.home() / ".claude" / "agents",
            "gemini": Path.home() / ".gemini" / "agents",
            "antigravity": Path.home() / ".gemini" / "config" / "agents",
        }
        for host, directory in targets.items():
            agents[host] = []
            source_dir = release / "adapters" / host / "agents"
            for source_file in sorted(source_dir.iterdir()):
                target = directory / source_file.name
                _copy(source_file, target, prepare)
                installed.append(target)
                agents[host].append(str(target))
        marketplace = _marketplace(prepare)
        installed.append(marketplace)
        prepare(_active_path())
        _atomic_json(_active_path(), active)
        install_manifest = config_dir() / "install-manifest.json"
        prepare(install_manifest)
        _atomic_json(
            install_manifest,
            {
                "schema_version": 2,
                "version": manifest["version"],
                "plugin_root": str(release),
                "release_manifest": str(_release_manifest_path(release)),
                "paths": [
                    {"path": str(path), "sha256": _hash(path)} for path in installed
                ],
            },
        )
    return {
        "installed": True,
        "version": manifest["version"],
        "plugin": PLUGIN_NAME,
        "release": str(release),
        "release_manifest": str(_release_manifest_path(release)),
        "runtime": str(runtime),
        "runtime_isolated": bool(manifest.get("runtime_isolated")),
        "environment": str(config_dir() / ".env"),
        "configuration": str(config_dir() / "config.toml"),
        "commands": ["sunday", "sunday-friday-mcp"],
        "agents": agents,
    }


@_serialized_installation
def install(
    source: str | Path | None = None,
    *,
    version: str | None = None,
    development: bool = False,
    isolated: bool = True,
    archive_sha256: str | None = None,
    source_description: str | None = None,
) -> dict:
    """Install a source tree as an immutable user-global release.

    ``development=True`` is the explicit checkout-linked fallback.
    """
    source_path = Path(source or ROOT).expanduser().resolve()
    if not (source_path / "sunday").is_dir() or not (source_path / "scripts").is_dir():
        raise RuntimeError(f"Invalid Sunday source tree: {source_path}")
    release_version = _source_version(source_path, version)
    if development:
        _smoke_test(source_path, Path(sys.executable))
        manifest = _release_manifest(
            source_path,
            release_version,
            sys.executable,
            False,
            source_description or "development-checkout",
            archive_sha256,
            "explicit development installation",
        )
        return _activate_release(source_path, manifest)

    destination = releases_dir() / release_version
    existing_manifest = _release_manifest_path(destination)
    if destination.is_dir() and existing_manifest.is_file():
        manifest = _read_json(existing_manifest)
        if manifest.get("version") != release_version:
            raise RuntimeError(
                f"Release directory has a mismatched manifest: {destination}"
            )
        _smoke_test(destination, _runtime_path(destination, manifest))
        return _activate_release(destination, manifest)
    if destination.exists():
        raise RuntimeError(f"Release destination already exists: {destination}")

    releases_dir().mkdir(parents=True, exist_ok=True)
    staging_root = Path(mkdtemp(prefix=".staging-", dir=releases_dir()))
    staged = staging_root / "release"
    try:
        shutil.copytree(source_path, staged, ignore=COPY_IGNORE)
        runtime, runtime_isolated, fallback_reason = _prepare_runtime(staged, isolated)
        manifest = _release_manifest(
            destination,
            release_version,
            runtime,
            runtime_isolated,
            source_description or f"local:{source_path}",
            archive_sha256,
            fallback_reason,
        )
        _atomic_json(_release_manifest_path(staged), manifest)
        os.replace(staged, destination)
    finally:
        if staging_root.exists():
            _remove_tree(staging_root)
    _smoke_test(destination, _runtime_path(destination, manifest))
    return _activate_release(destination, manifest)


@_serialized_installation
def uninstall() -> dict:
    manifest_path = config_dir() / "install-manifest.json"
    if not manifest_path.is_file():
        return {"uninstalled": False, "reason": "install manifest not found"}
    data = _read_json(manifest_path)
    removed: list[str] = []
    preserved: list[str] = []
    for item in reversed(data.get("paths", [])):
        path = Path(item["path"])
        if path.name == "marketplace.json":
            if path.is_file():
                market = _read_json(path)
                market["plugins"] = [
                    entry
                    for entry in market.get("plugins", [])
                    if entry.get("name") != PLUGIN_NAME
                ]
                _atomic_json(path, market)
                removed.append(str(path) + " entry")
            continue
        if path.is_symlink():
            path.unlink()
            removed.append(str(path))
        elif path.is_dir():
            _remove_tree(path)
            removed.append(str(path))
        elif path.is_file() and (
            not item.get("sha256") or _hash(path) == item["sha256"]
        ):
            path.unlink()
            removed.append(str(path))
        elif path.exists():
            preserved.append(str(path))
    _active_path().unlink(missing_ok=True)
    if releases_dir().is_dir():
        _remove_tree(releases_dir())
        removed.append(str(releases_dir()))
    manifest_path.unlink(missing_ok=True)
    return {"uninstalled": True, "removed": removed, "preserved_modified": preserved}


def _open_url(url: str, opener=None):
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": PLUGIN_NAME},
    )
    function = opener or urllib.request.urlopen
    try:
        return function(request, timeout=30)
    except TypeError:
        return function(request)


def _read_url(url: str, opener=None, limit: int = MAX_DOWNLOAD_BYTES) -> bytes:
    try:
        response = _open_url(url, opener)
        with response:
            data = response.read(limit + 1)
    except Exception as error:
        raise RuntimeError(
            f"Unable to download Sunday release data from {url}: {error}"
        ) from error
    if len(data) > limit:
        raise RuntimeError(f"Sunday release download exceeds {limit} bytes")
    return data


def _github_release(repository: str, opener=None) -> dict:
    api = os.environ.get("SUNDAY_RELEASE_API", GITHUB_API).rstrip("/")
    url = f"{api}/repos/{repository}/releases/latest"
    try:
        release = json.loads(_read_url(url, opener).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(
            "GitHub returned an invalid Sunday release response"
        ) from error
    if not isinstance(release, dict) or not release.get("tag_name"):
        raise RuntimeError("GitHub returned an invalid Sunday release response")
    return release


def _asset_url(release: dict, name: str) -> str | None:
    for asset in release.get("assets", []):
        if asset.get("name") == name and asset.get("browser_download_url"):
            return str(asset["browser_download_url"])
    return None


def _release_details(release: dict) -> dict:
    tag = str(release["tag_name"])
    version = _safe_version(tag)
    archive_name = f"{PLUGIN_NAME}-{tag}.zip"
    archive_url = _asset_url(release, archive_name)
    checksum_url = _asset_url(release, archive_name + ".sha256")
    if not archive_url or not checksum_url:
        raise RuntimeError(
            f"GitHub release {tag} lacks {archive_name} and its checksum"
        )
    return {
        "latest_version": version,
        "tag": tag,
        "archive_name": archive_name,
        "archive_url": archive_url,
        "checksum_url": checksum_url,
        "published_at": release.get("published_at"),
    }


def _selected_repository(repository: str | None) -> str:
    load_env()
    return repository or os.environ.get("SUNDAY_RELEASE_REPOSITORY", GITHUB_REPOSITORY)


def _version_key(value: str) -> tuple:
    version = _safe_version(value)
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:[-.]([A-Za-z0-9.-]+))?", version)
    if not match:
        raise RuntimeError(f"Sunday release is not semantic versioned: {value}")
    prerelease = tuple(
        (0, int(item)) if item.isdigit() else (1, item)
        for item in (match.group(4) or "").split(".") if item
    )
    return (
        int(match.group(1)), int(match.group(2)), int(match.group(3)),
        0 if prerelease else 1, prerelease,
    )


def check_update(*, repository: str | None = None, opener=None) -> dict:
    """Return remote release metadata without changing installation state."""
    repository = _selected_repository(repository)
    active = _read_json(_active_path()) if _active_path().is_file() else {}
    current = str(active.get("version") or __version__)
    details = _release_details(_github_release(repository, opener))
    return {
        "current_version": current,
        "installed": bool(active.get("release")),
        "update_available": not active.get("release")
        or _version_key(current) < _version_key(details["latest_version"]),
        **details,
    }


def _expected_checksum(value: bytes, archive_name: str) -> str:
    try:
        text = value.decode("ascii").strip()
    except UnicodeDecodeError as error:
        raise RuntimeError("Release checksum is not valid ASCII") from error
    match = re.fullmatch(r"([0-9a-fA-F]{64})(?:\s+\*?(.+))?", text)
    if not match:
        raise RuntimeError("Release checksum has an invalid format")
    if match.group(2) and Path(match.group(2)).name != archive_name:
        raise RuntimeError("Release checksum names a different archive")
    return match.group(1).lower()


def _extract_archive(archive: Path, destination: Path) -> Path:
    total = 0
    try:
        with zipfile.ZipFile(archive) as bundle:
            for item in bundle.infolist():
                name = item.filename.replace("\\", "/")
                path = PurePosixPath(name)
                mode = item.external_attr >> 16
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or (path.parts and ":" in path.parts[0])
                    or stat.S_ISLNK(mode)
                ):
                    raise RuntimeError(
                        f"Unsafe path in Sunday release archive: {item.filename}"
                    )
                total += item.file_size
                if total > MAX_ARCHIVE_BYTES:
                    raise RuntimeError("Sunday release archive is too large")
            bundle.extractall(destination)
    except zipfile.BadZipFile as error:
        raise RuntimeError("Sunday release archive is not a valid ZIP file") from error
    if (destination / "sunday").is_dir():
        return destination
    roots = [path for path in destination.iterdir() if path.is_dir()]
    if len(roots) == 1 and (roots[0] / "sunday").is_dir():
        return roots[0]
    raise RuntimeError("Sunday release archive has an invalid layout")


def _verify_provenance(archive: Path, repository: str) -> None:
    executable = shutil.which("gh")
    if not executable:
        raise RuntimeError("GitHub CLI is required to verify release provenance")
    result = subprocess.run(
        [executable, "attestation", "verify", str(archive), "--repo", repository],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise RuntimeError(f"Sunday release provenance verification failed: {detail}")


@_serialized_installation
def update(*, repository: str | None = None, opener=None) -> dict:
    """Download, verify, stage, test, and atomically activate a release."""
    repository = _selected_repository(repository)
    details = check_update(repository=repository, opener=opener)
    if not details["update_available"]:
        return {
            "updated": False,
            "reason": "already current",
            "version": details["current_version"],
        }
    archive_bytes = _read_url(details["archive_url"], opener)
    checksum_bytes = _read_url(details["checksum_url"], opener, 4096)
    expected = _expected_checksum(checksum_bytes, details["archive_name"])
    actual = hashlib.sha256(archive_bytes).hexdigest()
    if actual != expected:
        raise RuntimeError(
            f"Sunday release checksum mismatch: expected {expected}, received {actual}"
        )
    with TemporaryDirectory(prefix="sunday-download-") as temp:
        temporary = Path(temp)
        archive = temporary / details["archive_name"]
        archive.write_bytes(archive_bytes)
        if opener is None:
            _verify_provenance(archive, repository)
        extracted = temporary / "extracted"
        extracted.mkdir()
        source = _extract_archive(archive, extracted)
        installed = install(
            source,
            version=details["latest_version"],
            archive_sha256=actual,
            source_description=details["archive_url"],
        )
    return {
        **installed,
        "updated": True,
        "previous_version": details["current_version"],
    }


@_serialized_installation
def rollback(version: str | None = None) -> dict:
    """Atomically reactivate the previous retained release."""
    active_path = _active_path()
    if not active_path.is_file():
        return {"rolled_back": False, "reason": "active release not found"}
    active = _read_json(active_path)
    requested = _safe_version(version) if version else None
    candidate = None
    for item in active.get("history", []):
        if not isinstance(item, dict):
            continue
        if (
            requested is None
            or _safe_version(str(item.get("version", ""))) == requested
        ):
            candidate = item
            break
    if candidate is None:
        return {"rolled_back": False, "reason": "rollback release not found"}
    release = Path(str(candidate["release"]))
    manifest_path = _release_manifest_path(release)
    if not release.is_dir() or not manifest_path.is_file():
        return {"rolled_back": False, "reason": "rollback release is unavailable"}
    manifest = _read_json(manifest_path)
    _smoke_test(release, _runtime_path(release, manifest))
    previous = str(active.get("version"))
    result = _activate_release(release, manifest)
    return {**result, "rolled_back": True, "previous_version": previous}
