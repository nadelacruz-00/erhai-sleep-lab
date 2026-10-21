# SPDX-License-Identifier: GPL-2.0-only
"""arm/disarm: the suspend override exists only while armed (D19, D14, D9)."""

import tempfile
import unittest
from pathlib import Path

from labtool import lab


class DropIn(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name) / "systemd-suspend.service.d"
        self.d.mkdir()
        # The dev's own override must survive arm/disarm untouched.
        self.dev = self.d / "erhai-s2idle.conf"
        self.dev.write_text("[Service]\nExecStart=\nExecStart=/usr/local/sbin/erhai-suspend-gnome.sh\n")

    def tearDown(self):
        self._tmp.cleanup()

    def test_arm_writes_override_that_sorts_after_the_devs(self):
        path = lab.arm(self.d, reload=False)
        self.assertEqual(path.name, "zz-erhai-lab.conf")
        self.assertGreater(path.name, self.dev.name)
        text = path.read_text()
        self.assertIn("ExecStart=\n", text)
        self.assertIn("ExecStart=/usr/lib/systemd/systemd-sleep suspend", text)
        self.assertIn("SYSTEMD_SLEEP_FREEZE_USER_SESSIONS=false", text)

    def test_disarm_removes_only_the_lab_override(self):
        lab.arm(self.d, reload=False)
        before = self.dev.read_text()
        self.assertTrue(lab.disarm(self.d, reload=False))
        self.assertEqual(sorted(p.name for p in self.d.iterdir()), ["erhai-s2idle.conf"])
        self.assertEqual(self.dev.read_text(), before)

    def test_disarm_is_idempotent(self):
        self.assertFalse(lab.disarm(self.d, reload=False))
        self.assertFalse(lab.disarm(self.d, reload=False))


if __name__ == "__main__":
    unittest.main()
