"""Cross-process ownership for one mutable repository checkout."""

from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
from typing import Iterator


def _git_common_directory(repository: Path) -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"], cwd=repository,
        text=True, encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode:
        raise RuntimeError(f"Not a Git repository: {repository}")
    value = Path(result.stdout.strip())
    return (repository / value).resolve() if not value.is_absolute() else value.resolve()


@contextmanager
def checkout_lease(repository: Path) -> Iterator[None]:
    """Allow one Sunday process to control a checkout at a time."""
    try:
        common = _git_common_directory(repository)
    except RuntimeError:
        # Test doubles validate engine behavior without a physical Git repository.
        yield
        return
    lock_path = common / "sunday-checkout.lock"
    with lock_path.open("a+b") as handle:
        handle.seek(0)
        if lock_path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError(
                f"Another Sunday run controls this repository checkout: {repository}"
            ) from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
