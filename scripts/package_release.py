#!/usr/bin/env python3.11
"""Build portable release zip archive with synchronized manifest versions."""

import os
import pathlib
import subprocess
import zipfile


def main() -> None:
    ref_name = os.environ.get("GITHUB_REF_NAME", "v1.0.5")
    archive = f"sunday-agentic-flow-{ref_name}.zip"
    prefix = "sunday-agentic-flow/"

    root = pathlib.Path(__file__).resolve().parent.parent

    subprocess.run(
        ["git", "archive", "--format=zip", f"--prefix={prefix}", "--output", archive, "HEAD"],
        cwd=root,
        check=True,
    )

    files_to_update = {
        "VERSION": (root / "VERSION").read_bytes(),
        "pyproject.toml": (root / "pyproject.toml").read_bytes(),
        ".codex-plugin/plugin.json": (root / ".codex-plugin" / "plugin.json").read_bytes(),
        ".claude-plugin/plugin.json": (root / ".claude-plugin" / "plugin.json").read_bytes(),
        "gemini-extension.json": (root / "gemini-extension.json").read_bytes(),
    }
    target_names = {f"{prefix}{rel}" for rel in files_to_update}

    zip_path = root / archive
    temp_zip = zip_path.with_suffix(".zip.tmp")

    with zipfile.ZipFile(zip_path, "r") as zin, zipfile.ZipFile(temp_zip, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename not in target_names:
                zout.writestr(item, zin.read(item.filename))
        for rel_path, data in files_to_update.items():
            zout.writestr(f"{prefix}{rel_path}", data)

    temp_zip.replace(zip_path)
    print(f"Successfully packaged {zip_path}")


if __name__ == "__main__":
    main()
