import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import sunday.installation as installation


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.install_root = self.home / ".local" / "share" / "sunday"
        self.patches = (
            patch.object(Path, "home", return_value=self.home),
            patch.dict(
                os.environ,
                {"SUNDAY_INSTALL_DIR": str(self.install_root)},
                clear=False,
            ),
            patch.object(
                installation,
                "config_dir",
                return_value=self.home / ".config" / "sunday",
            ),
            patch.object(
                installation, "bin_dir", return_value=self.home / ".local" / "bin"
            ),
        )
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def make_source(self, version: str) -> Path:
        source = self.home / f"source-{version}"
        (source / "sunday").mkdir(parents=True)
        (source / "sunday" / "__init__.py").write_text("", encoding="utf-8")
        (source / "scripts").mkdir()
        (source / "scripts" / "sunday.py").write_text(
            "print('Sunday test launcher')\n", encoding="utf-8"
        )
        (source / "scripts" / "friday_mcp_proxy.py").write_text(
            "print('Sunday test bridge')\n", encoding="utf-8"
        )
        for host in ("codex", "claude", "gemini", "antigravity"):
            agents = source / "adapters" / host / "agents"
            agents.mkdir(parents=True)
            (agents / f"{host}-agent.txt").write_text(host, encoding="utf-8")
        (source / "VERSION").write_text(version + "\n", encoding="utf-8")
        return source

    def release_archive(self, source: Path, tag: str) -> bytes:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as bundle:
            for path in source.rglob("*"):
                if path.is_file():
                    relative = path.relative_to(source)
                    bundle.write(path, f"sunday-agentic-flow/{relative.as_posix()}")
        return output.getvalue()

    def fake_release_opener(
        self, archive: bytes, tag: str = "v2.0.0",
        repository: str = "gabefonsecas/sunday-agentic-flow",
    ):
        archive_name = f"sunday-agentic-flow-{tag}.zip"
        archive_url = f"https://downloads.example/{archive_name}"
        checksum_url = archive_url + ".sha256"
        release = json.dumps(
            {
                "tag_name": tag,
                "published_at": "2026-08-11T00:00:00Z",
                "assets": [
                    {"name": archive_name, "browser_download_url": archive_url},
                    {
                        "name": archive_name + ".sha256",
                        "browser_download_url": checksum_url,
                    },
                ],
            }
        ).encode()
        checksum = f"{hashlib.sha256(archive).hexdigest()}  {archive_name}\n".encode()
        responses = {
            f"https://api.github.com/repos/{repository}/releases/latest": release,
            archive_url: archive,
            checksum_url: checksum,
        }

        def open_response(request, timeout=30):
            self.assertEqual(timeout, 30)
            return io.BytesIO(responses[request.full_url])

        return open_response

    def test_install_and_uninstall_managed_files(self):
        result = installation.install()
        self.assertTrue(result["installed"])
        launcher = "sunday.cmd" if os.name == "nt" else "sunday"
        self.assertTrue((self.home / ".local" / "bin" / launcher).is_file())
        self.assertTrue((self.home / ".config" / "sunday" / "config.toml").is_file())
        marketplace = json.loads(
            (self.home / ".agents" / "plugins" / "marketplace.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(marketplace["plugins"][0]["name"], "sunday-agentic-flow")
        removed = installation.uninstall()
        self.assertTrue(removed["uninstalled"])
        self.assertFalse((self.home / ".local" / "bin" / launcher).exists())
        self.assertTrue((self.home / ".config" / "sunday" / ".env").exists())

    def test_install_rolls_back_when_marketplace_fails(self):
        with patch.object(
            installation, "_marketplace", side_effect=RuntimeError("broken")
        ):
            with self.assertRaisesRegex(RuntimeError, "broken"):
                installation.install()
        launcher = "sunday.cmd" if os.name == "nt" else "sunday"
        self.assertFalse((self.home / ".local" / "bin" / launcher).exists())

    def test_install_uses_versioned_release_and_preserves_configuration(self):
        source = self.make_source("1.2.3")
        env = self.home / ".config" / "sunday" / ".env"
        env.parent.mkdir(parents=True)
        env.write_text("FRIDAY_API_TOKEN=secret\n", encoding="utf-8")

        result = installation.install(source, isolated=False)

        release = self.home / ".local" / "share" / "sunday" / "releases" / "1.2.3"
        manifest = json.loads(
            (release / "release-manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(Path(result["release"]), release)
        self.assertEqual(manifest["version"], "1.2.3")
        self.assertEqual(manifest["smoke_test"], "passed")
        self.assertFalse(manifest["runtime_isolated"])
        self.assertEqual(env.read_text(encoding="utf-8"), "FRIDAY_API_TOKEN=secret\n")

    def test_update_downloads_verified_release_then_rollback_reactivates_previous(self):
        first = self.make_source("1.0.0")
        installation.install(first, isolated=False)
        env = self.home / ".config" / "sunday" / ".env"
        env.write_text("FRIDAY_API_TOKEN=keep-me\n", encoding="utf-8")
        second = self.make_source("2.0.0")
        archive = self.release_archive(second, "v2.0.0")
        opener = self.fake_release_opener(archive)

        with patch.object(
            installation,
            "_prepare_runtime",
            return_value=(installation.sys.executable, False, "test runtime"),
        ):
            result = installation.update(opener=opener)

        self.assertTrue(result["updated"])
        self.assertEqual(result["version"], "2.0.0")
        active = json.loads(
            (
                self.home / ".local" / "share" / "sunday" / "active-release.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(active["version"], "2.0.0")
        release_manifest = json.loads(
            Path(result["release_manifest"]).read_text(encoding="utf-8")
        )
        self.assertEqual(
            release_manifest["archive_sha256"], hashlib.sha256(archive).hexdigest()
        )
        self.assertEqual(env.read_text(encoding="utf-8"), "FRIDAY_API_TOKEN=keep-me\n")

        rolled_back = installation.rollback()

        self.assertTrue(rolled_back["rolled_back"])
        self.assertEqual(rolled_back["version"], "1.0.0")
        self.assertEqual(
            Path(rolled_back["release"]),
            self.install_root / "releases" / "1.0.0",
        )

    def test_update_rejects_bad_checksum_before_staging(self):
        first = self.make_source("1.0.0")
        installation.install(first, isolated=False)
        second = self.make_source("2.0.0")
        archive = self.release_archive(second, "v2.0.0")
        opener = self.fake_release_opener(archive)

        def corrupted(request, timeout=30):
            response = opener(request, timeout)
            if request.full_url.endswith(".sha256"):
                return io.BytesIO(("0" * 64 + "\n").encode())
            return response

        with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
            installation.update(opener=corrupted)

        active = json.loads(
            (
                self.home / ".local" / "share" / "sunday" / "active-release.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(active["version"], "1.0.0")
        self.assertFalse(
            (self.home / ".local" / "share" / "sunday" / "releases" / "2.0.0").exists()
        )

    def test_release_repository_can_come_from_environment(self):
        source = self.make_source("2.0.0")
        archive = self.release_archive(source, "v2.0.0")
        repository = "company/internal-sunday"
        opener = self.fake_release_opener(archive, repository=repository)
        with patch.dict(
            os.environ, {"SUNDAY_RELEASE_REPOSITORY": repository}, clear=False
        ):
            result = installation.check_update(opener=opener)
        self.assertEqual(result["latest_version"], "2.0.0")

    def test_update_check_never_downgrades_a_newer_installation(self):
        installation.install(self.make_source("3.0.0"))
        older = self.make_source("2.0.0")
        archive = self.release_archive(older, "v2.0.0")
        result = installation.check_update(
            opener=self.fake_release_opener(archive, tag="v2.0.0")
        )
        self.assertEqual(result["current_version"], "3.0.0")
        self.assertEqual(result["latest_version"], "2.0.0")
        self.assertFalse(result["update_available"])

    def test_semver_prerelease_numeric_identifiers_are_ordered_numerically(self):
        self.assertLess(
            installation._version_key("1.0.0-rc.2"),
            installation._version_key("1.0.0-rc.10"),
        )
        self.assertLess(
            installation._version_key("1.0.0-rc.10"),
            installation._version_key("1.0.0"),
        )
