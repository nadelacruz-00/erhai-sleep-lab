# SPDX-License-Identifier: GPL-2.0-only
"""ci/assert-config.sh: a symbol dropped by olddefconfig fails the build."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from labtool import REPO_ROOT

SCRIPT = REPO_ROOT / "ci" / "assert-config.sh"


def run(frag: str, config: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "extra.config"
        c = Path(tmp) / ".config"
        f.write_text(frag)
        c.write_text(config)
        return subprocess.run(["bash", str(SCRIPT), str(f), str(c)],
                              capture_output=True, text=True)


class AssertConfig(unittest.TestCase):
    def test_all_present(self):
        r = run("CONFIG_PM_DEBUG=y\n# CONFIG_FOO is not set\n",
                "CONFIG_PM_DEBUG=y\n# CONFIG_FOO is not set\nCONFIG_BAR=m\n")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_dropped_symbol_fails(self):
        r = run("CONFIG_DPM_WATCHDOG=y\n", "CONFIG_PM_DEBUG=y\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("CONFIG_DPM_WATCHDOG=y", r.stderr)

    def test_changed_value_fails(self):
        r = run("CONFIG_DPM_WATCHDOG_TIMEOUT=60\n", "CONFIG_DPM_WATCHDOG_TIMEOUT=120\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("got 'CONFIG_DPM_WATCHDOG_TIMEOUT=120'", r.stderr)

    def test_shipped_fragment_is_well_formed(self):
        frag = (REPO_ROOT / "candidates" / "00-debug" / "extra.config").read_text()
        for line in frag.splitlines():
            self.assertRegex(line, r"^(CONFIG_[A-Z0-9_]+=.+|# CONFIG_[A-Z0-9_]+ is not set)$")


if __name__ == "__main__":
    unittest.main()
