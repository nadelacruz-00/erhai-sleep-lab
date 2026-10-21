# SPDX-License-Identifier: GPL-2.0-only
"""Wi-Fi L1 rebind: cnss_pci bind alone does not bring the host driver back."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from labtool import lab


def attempt():
    return lab.Attempt(bootid="b", ts=5.0, rung="dry", wifi="L1")


class FakeTablet:
    """sysfs dirs under a temp root; run/sysfs_write/wlan_state recorded."""

    def __init__(self, root: Path, wlan_loaded=True, netdev_after_reload=True):
        self.pci = root / "pci-devices"
        self.cnss = root / "cnss_pci"
        self.module = root / "module-wlan"
        (self.pci / lab.WIFI_BDF).mkdir(parents=True)
        self.cnss.mkdir()
        if wlan_loaded:
            self.module.mkdir()
        self.netdev = False
        self.netdev_after_reload = netdev_after_reload
        self.cmds = []

    def run(self, cmd, timeout):
        self.cmds.append(cmd)
        if cmd[0] == "modprobe":
            self.netdev = self.netdev_after_reload
        return ""

    def sysfs_write(self, path, value, timeout):
        self.cmds.append(["write", str(path), value])
        if path == self.cnss / "bind":
            (self.pci / lab.WIFI_BDF / "driver").mkdir()

    def wlan_state(self):
        return "disconnected" if self.netdev else "(no device)"

    def patches(self):
        return [mock.patch.object(lab, "PCI_DEVICES", self.pci),
                mock.patch.object(lab, "CNSS_DRIVER", self.cnss),
                mock.patch.object(lab, "WLAN_MODULE_DIR", self.module),
                mock.patch.object(lab, "run", self.run),
                mock.patch.object(lab, "sysfs_write", self.sysfs_write),
                mock.patch.object(lab, "wlan_state", self.wlan_state),
                mock.patch.object(lab.time, "sleep", lambda s: None)]


class RebindL1(unittest.TestCase):
    def run_rebind(self, tablet, saved):
        for p in tablet.patches():
            p.start()
            self.addCleanup(p.stop)
        lab.HookActions(attempt(), saved).wifi_rebind_l1(15)

    def test_binds_then_reloads_wlan_ko(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = FakeTablet(Path(tmp))
            self.run_rebind(t, {"l1_unbound": True})
            self.assertEqual(t.cmds, [
                ["write", str(t.cnss / "bind"), lab.WIFI_BDF],
                ["rmmod", "wlan"],
                ["modprobe", "wlan"]])

    def test_never_modprobe_r(self):
        # modprobe -r would take the unused cnss2 with it
        with tempfile.TemporaryDirectory() as tmp:
            t = FakeTablet(Path(tmp))
            self.run_rebind(t, {"l1_unbound": True})
            self.assertNotIn(["modprobe", "-r", "wlan"], t.cmds)

    def test_wlan_not_loaded_skips_rmmod(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = FakeTablet(Path(tmp), wlan_loaded=False)
            self.run_rebind(t, {"l1_unbound": True})
            self.assertEqual(t.cmds[1:], [["modprobe", "wlan"]])

    def test_no_netdev_after_reload_is_a_restore_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = FakeTablet(Path(tmp), netdev_after_reload=False)
            with mock.patch.object(lab.time, "monotonic", side_effect=[0, 0, 100]):
                with self.assertRaisesRegex(lab.StepFailed, "wlan.ko reload"):
                    self.run_rebind(t, {"l1_unbound": True})

    def test_nothing_when_not_unbound(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = FakeTablet(Path(tmp))
            self.run_rebind(t, {})
            self.assertEqual(t.cmds, [])


class Settle(unittest.TestCase):
    def test_missing_device_fails_at_once_with_the_remedy(self):
        with mock.patch.object(lab, "wlan_state", lambda: "(no device)"):
            with self.assertRaisesRegex(lab.StepFailed, "modprobe wlan"):
                lab.HookActions(attempt(), {}).wifi_settle(12)


if __name__ == "__main__":
    unittest.main()
