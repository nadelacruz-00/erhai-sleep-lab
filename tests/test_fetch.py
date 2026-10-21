# SPDX-License-Identifier: GPL-2.0-only
"""fetch: SHA256SUMS and asset verification (eng review D6)."""

import hashlib
import tempfile
import unittest
from pathlib import Path

from labtool import lab

KVER = "7.3.0-rc5-sm8750-themojoman-lab-00-debug"


def write_release(d: Path, kver: str = KVER, sums: bool = True,
                  corrupt: str | None = None) -> None:
    files = {
        f"{kver}.efi": b"uki",
        f"modules-{kver}.tar.zst": b"modules",
        f"config-{kver}": b"CONFIG_PM_DEBUG=y\n",
    }
    for name, data in files.items():
        (d / name).write_bytes(data)
    if sums:
        lines = [f"{hashlib.sha256(data).hexdigest()}  {name}"
                 for name, data in files.items()]
        (d / "SHA256SUMS").write_text("\n".join(lines) + "\n")
    if corrupt:
        (d / corrupt).write_bytes(b"tampered")


class VerifyAssets(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_intact_release_verifies_and_identifies(self):
        write_release(self.d)
        lab.verify_assets(self.d)
        a = lab.identify_assets(self.d, "00-debug")
        self.assertEqual(a.kver, KVER)
        self.assertEqual(a.uki.name, f"{KVER}.efi")

    def test_missing_sums_refuses(self):
        write_release(self.d, sums=False)
        with self.assertRaisesRegex(lab.LabError, "no SHA256SUMS"):
            lab.verify_assets(self.d)

    def test_checksum_mismatch_refuses(self):
        write_release(self.d, corrupt=f"{KVER}.efi")
        with self.assertRaisesRegex(lab.LabError, "checksum mismatch"):
            lab.verify_assets(self.d)

    def test_unlisted_file_refuses(self):
        write_release(self.d)
        (self.d / "extra.bin").write_bytes(b"x")
        with self.assertRaisesRegex(lab.LabError, "not listed"):
            lab.verify_assets(self.d)

    def test_listed_but_missing_refuses(self):
        write_release(self.d)
        (self.d / f"config-{KVER}").unlink()
        with self.assertRaisesRegex(lab.LabError, "not downloaded"):
            lab.verify_assets(self.d)

    def test_uki_modules_kver_mismatch_refuses(self):
        write_release(self.d)
        (self.d / f"modules-{KVER}.tar.zst").rename(
            self.d / "modules-7.3.0-rc5-sm8750-themojoman-lab-10-rails.tar.zst")
        with self.assertRaisesRegex(lab.LabError, "does not match"):
            lab.identify_assets(self.d, "00-debug")

    def test_wrong_candidate_refuses(self):
        write_release(self.d)
        with self.assertRaisesRegex(lab.LabError, "not a lab build"):
            lab.identify_assets(self.d, "10-rails-always-on")

    def test_package_kernelrelease_is_never_installed(self):
        a = lab.Assets("7.3.0-rc5-sm8750-themojoman", self.d / "a.efi",
                       self.d / "m.tar.zst", self.d / "c")
        with self.assertRaisesRegex(lab.LabError, "non-lab"):
            lab.install_assets(a, boot_dir=self.d, modules_dir=self.d)

    def test_malformed_sums_line_refuses(self):
        with self.assertRaisesRegex(lab.LabError, "malformed"):
            lab.parse_sums("not a checksum line\n")


class ReleaseAssets(unittest.TestCase):
    def test_picks_the_tagged_release(self):
        releases = [
            {"tag_name": "lab-00-debug-1", "assets": [{"name": "a", "browser_download_url": "u1"}]},
            {"tag_name": "lab-00-debug-2", "assets": [
                {"name": "x.efi", "browser_download_url": "u2"},
                {"name": "SHA256SUMS", "browser_download_url": "u3"}]},
        ]
        self.assertEqual(lab.release_assets(releases, "lab-00-debug-2"),
                         [("x.efi", "u2"), ("SHA256SUMS", "u3")])

    def test_missing_release_refuses(self):
        with self.assertRaisesRegex(lab.LabError, "not found"):
            lab.release_assets([], "lab-00-debug-9")


class LatestTag(unittest.TestCase):
    def test_highest_run_for_candidate(self):
        tags = ["lab-00-debug-3", "lab-00-debug-12", "lab-10-rails-always-on-40",
                "lab-00-debug-x", "v1"]
        self.assertEqual(lab.latest_tag(tags, "00-debug"), "lab-00-debug-12")

    def test_no_release_refuses(self):
        with self.assertRaisesRegex(lab.LabError, "no release"):
            lab.latest_tag(["lab-10-rails-always-on-1"], "00-debug")


if __name__ == "__main__":
    unittest.main()
