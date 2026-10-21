# SPDX-License-Identifier: GPL-2.0-only
"""Pre-sleep guard (D7) and the probe's refusals and verdicts."""

import json
import tempfile
import unittest
from pathlib import Path

from labtool import lab


def attempt(**kw):
    base = dict(bootid="b", ts=5.0, rung="E2", wifi="L2", display="park", alarm_s=30)
    base.update(kw)
    return lab.Attempt(**base)


class FakeSystem:
    def __init__(self, fail_on=None, raise_exc=lab.StepFailed("boom")):
        self.fail_on = fail_on
        self.raise_exc = raise_exc
        self.calls = []
        self.freezer = 0
        self.journal = []

    def do(self, name, budget):
        self.calls.append(name)
        if name == self.fail_on:
            raise self.raise_exc

    def set_freezer(self):
        self.freezer += 1


class RunPre(unittest.TestCase):
    def test_clean_run_completes_every_step(self):
        sys_ = FakeSystem()
        state = lab.run_pre(attempt(), sys_.do, sys_.set_freezer, sys_.journal.append)
        self.assertIsNone(state["aborted"])
        self.assertEqual(state["completed"], [s.name for s in lab.pre_plan(attempt())])
        self.assertEqual(sys_.freezer, 0)
        self.assertEqual(sys_.journal, [])

    def test_failure_sets_freezer_undoes_in_reverse_and_journals(self):
        sys_ = FakeSystem(fail_on="wifi-unbind-l2")
        state = lab.run_pre(attempt(), sys_.do, sys_.set_freezer, sys_.journal.append)
        self.assertEqual(state["aborted"], "pre-wifi-unbind-l2")
        self.assertEqual(sys_.freezer, 1)
        # nothing after the failing step ran; undo ran in reverse order
        self.assertEqual(sys_.calls, [
            "display-park", "watcher-stop", "psoc-timer-freeze", "wifi-settle",
            "wifi-unbind-l1", "wifi-unbind-l2",
            "wifi-rebind-l1", "psoc-timer-restore", "watcher-start", "display-unpark"])
        self.assertEqual(sys_.journal[0]["event"], "abort")
        self.assertEqual(sys_.journal[0]["step"], "pre-wifi-unbind-l2")

    def test_alarm_failure_is_guarded_like_any_step(self):
        sys_ = FakeSystem(fail_on="alarm-arm")
        state = lab.run_pre(attempt(), sys_.do, sys_.set_freezer, sys_.journal.append)
        self.assertEqual(state["aborted"], "pre-alarm-arm")
        self.assertEqual(sys_.freezer, 1)
        self.assertNotIn("alarm-clear", sys_.calls)

    def test_unexpected_exception_still_aborts_cleanly(self):
        sys_ = FakeSystem(fail_on="watcher-stop", raise_exc=RuntimeError("bug"))
        state = lab.run_pre(attempt(), sys_.do, sys_.set_freezer, sys_.journal.append)
        self.assertEqual(state["aborted"], "pre-watcher-stop")
        self.assertEqual(sys_.calls[-1], "display-unpark")

    def test_undo_errors_are_recorded_not_raised(self):
        class Flaky(FakeSystem):
            def do(self, name, budget):
                super().do(name, budget)
                if name == "display-unpark":
                    raise lab.StepFailed("session gone")
        sys_ = Flaky(fail_on="sync")
        state = lab.run_pre(attempt(), sys_.do, sys_.set_freezer, sys_.journal.append)
        self.assertEqual(state["undo_errors"], ["display-unpark: session gone"])


class JournalWrite(unittest.TestCase):
    def test_writes_mirror_even_without_pmsg(self):
        with tempfile.TemporaryDirectory() as tmp:
            mirror = Path(tmp) / "state" / "journal.jsonl"
            lab.journal_write({"event": "x"}, pmsg=Path(tmp) / "no" / "pmsg0", mirror=mirror)
            lab.journal_write({"event": "y"}, pmsg=Path(tmp) / "no" / "pmsg0", mirror=mirror)
            lines = [json.loads(l) for l in mirror.read_text().splitlines()]
            self.assertEqual([l["event"] for l in lines], ["x", "y"])
            self.assertIn("wall", lines[0])


class ProbeRefusals(unittest.TestCase):
    def test_refuses_e0_and_real_sleep_in_wave_1a(self):
        with self.assertRaisesRegex(lab.LabError, "manual rung"):
            lab.check_probe_request("E0", 0, True, "00-debug")
        for rung in ("E5", "E6", "E7"):
            with self.assertRaisesRegex(lab.LabError, "real-sleep"):
                lab.check_probe_request(rung, 120, True, "00-debug")

    def test_refuses_without_pm_test_or_lab_kernel(self):
        with self.assertRaisesRegex(lab.LabError, "pm_test"):
            lab.check_probe_request("E1", 0, False, "00-debug")
        with self.assertRaisesRegex(lab.LabError, "lab kernel"):
            lab.check_probe_request("E1", 0, True, "")

    def test_e4_5_needs_an_alarm(self):
        with self.assertRaisesRegex(lab.LabError, "alarm"):
            lab.check_probe_request("E4.5", 0, True, "00-debug")
        lab.check_probe_request("E4.5", 30, True, "00-debug")

    def test_pm_test_levels(self):
        self.assertEqual(lab.PM_TEST["E1"], "freezer")
        self.assertEqual(lab.PM_TEST["E3"], "devices")
        self.assertEqual(lab.PM_TEST["E4"], "platform")
        self.assertEqual(lab.PM_TEST["E4.5"], "platform")


class WifiRemovalSuspended(unittest.TestCase):
    def test_l1_l2_refused_without_override(self):
        for level in ("L1", "L2"):
            with self.assertRaisesRegex(lab.LabError, "hif_exec_napi_kill"):
                lab.check_wifi_level(level, False)
            lab.check_wifi_level(level, True)
        lab.check_wifi_level("keep", False)


class PmTestHold(unittest.TestCase):
    def test_hold_outlasts_the_alarm(self):
        self.assertEqual(lab.pm_test_hold("platform", 30), 40)

    def test_no_change_without_alarm_or_for_real_sleep(self):
        self.assertIsNone(lab.pm_test_hold("platform", 0))
        self.assertIsNone(lab.pm_test_hold("none", 120))


class Verdict(unittest.TestCase):
    B = {"success": "3", "fail": "0"}

    def test_pass(self):
        self.assertEqual(lab.pm_test_verdict("E2", self.B, {"success": "4", "fail": "0"},
                                             None, {}, {}), "pass")

    def test_abort_wins(self):
        self.assertTrue(lab.pm_test_verdict("E2", self.B, {"success": "4", "fail": "0"},
                                            "pre-wifi-settle", {}, {}).startswith("abort"))

    def test_fail_names_step_and_device(self):
        v = lab.pm_test_verdict("E3", self.B, {"success": "3", "fail": "1",
                                               "last_failed_step": "suspend",
                                               "last_failed_dev": "cnss_pci"}, None, {}, {})
        self.assertIn("cnss_pci", v)
        self.assertTrue(v.startswith("fail"))

    def test_resume_error_is_not_a_pass(self):
        before = {"success": "3", "fail": "0", "failed_resume": "0"}
        after = {"success": "4", "fail": "0", "failed_resume": "1",
                 "last_failed_dev": "0000:01:00.0"}
        v = lab.pm_test_verdict("E2", before, after, None, {}, {})
        self.assertTrue(v.startswith("fail (resume errors"), v)
        self.assertIn("0000:01:00.0", v)

    def test_e4_5_requires_alarm_irq(self):
        after = {"success": "4", "fail": "0"}
        self.assertTrue(lab.pm_test_verdict("E4.5", self.B, after, None,
                                            {"pm8xxx_rtc_alarm": 2},
                                            {"pm8xxx_rtc_alarm": 2}).startswith("fail"))
        self.assertEqual(lab.pm_test_verdict("E4.5", self.B, after, None,
                                             {"pm8xxx_rtc_alarm": 2},
                                             {"pm8xxx_rtc_alarm": 3}), "pass")


class WlanEvents(unittest.TestCase):
    LOG = ("[1] cnss: Doing idle shutdown\n[2] erhai-lab probe 100\n"
           "[3] cnss: Doing idle shutdown\n[4] Internal error: Oops: 96000004 [#1]\n"
           "[5] cnss: Doing idle restart\n")

    def test_counts_only_after_the_marker(self):
        self.assertEqual(lab.wlan_events_since(self.LOG, "erhai-lab probe 100"),
                         {"idle_shutdown": 1, "idle_restart": 1, "oops": 1})

    def test_missing_marker_counts_nothing(self):
        self.assertEqual(lab.wlan_events_since(self.LOG, "erhai-lab probe 999"),
                         {"idle_shutdown": 0, "idle_restart": 0, "oops": 0})


class WlanIni(unittest.TestCase):
    def test_reads_key_and_unset(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            ini = Path(tmp) / "WCNSS_qcom_cfg.ini"
            ini.write_text("# c\ngEnableDebugLog=0\ngInterfaceChangeWait = 0\nEND\n")
            self.assertEqual(lab.wlan_ini_value("gInterfaceChangeWait", ini), "0")
            self.assertIsNone(lab.wlan_ini_value("gScanNumProbes", ini))
            self.assertIsNone(lab.wlan_ini_value("x", Path(tmp) / "missing.ini"))


class WakeupDiff(unittest.TestCase):
    def test_only_changed_sources(self):
        before = {"pwrkey": [0, 0], "rtc": [2, 2], "wlan": [4, 0]}
        after = {"pwrkey": [1, 1], "rtc": [2, 2], "wlan": [9, 0], "new": [1, 0]}
        self.assertEqual(lab.wakeup_diff(before, after),
                         {"pwrkey": [1, 1], "wlan": [5, 0], "new": [1, 0]})


if __name__ == "__main__":
    unittest.main()
