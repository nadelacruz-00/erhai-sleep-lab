# SPDX-License-Identifier: GPL-2.0-only
"""Hook step plan: order, guards and undo (D7, D13, D15, D16, D19)."""

import unittest

from labtool import lab


def attempt(**kw):
    base = dict(bootid="b", ts=0.0, rung="E2")
    base.update(kw)
    return lab.Attempt(**base)


def names(steps):
    return [s.name for s in steps]


class PrePlan(unittest.TestCase):
    def test_no_attempt_means_no_steps(self):
        # Outside an armed attempt the hook is inert (D19).
        self.assertEqual(lab.pre_plan(None), [])
        self.assertEqual(lab.post_plan(None), [])

    def test_display_goes_first_and_alarm_last(self):
        plan = names(lab.pre_plan(attempt(wifi="L2", display="park", alarm_s=120)))
        self.assertEqual(plan[0], "display-park")
        self.assertEqual(plan[-1], "alarm-arm")
        self.assertEqual(plan, ["display-park", "watcher-stop", "psoc-timer-freeze",
                                "wifi-settle", "wifi-unbind-l1", "wifi-unbind-l2",
                                "sync", "journal", "alarm-arm"])

    def test_backlight_mode_and_kept_wifi(self):
        plan = names(lab.pre_plan(attempt()))
        self.assertEqual(plan, ["display-off", "watcher-stop", "psoc-timer-freeze",
                                "sync", "journal"])

    def test_l1_does_not_unbind_pwrctrl(self):
        plan = names(lab.pre_plan(attempt(wifi="L1")))
        self.assertIn("wifi-unbind-l1", plan)
        self.assertNotIn("wifi-unbind-l2", plan)
        self.assertLess(plan.index("wifi-settle"), plan.index("wifi-unbind-l1"))

    def test_never_issues_a_radio_off(self):
        # NetworkManager does its own radio-off on PrepareForSleep; a second
        # one raced it and crashed the WCN stack (D15).
        for wifi in lab.WIFI_LEVELS:
            for step in lab.pre_plan(attempt(wifi=wifi, alarm_s=30)):
                self.assertNotIn("radio", step.name)

    def test_every_step_has_a_budget(self):
        for s in lab.pre_plan(attempt(wifi="L2", display="park", alarm_s=30)):
            self.assertGreater(s.budget_s, 0)

    def test_settle_keeps_the_harness_window(self):
        settle = [s for s in lab.pre_plan(attempt(wifi="L1")) if s.name == "wifi-settle"]
        self.assertEqual(settle[0].budget_s, 12.0)


class Undo(unittest.TestCase):
    def test_undo_reverses_completed_steps(self):
        pre = lab.pre_plan(attempt(wifi="L2", display="park", alarm_s=30))
        completed = pre[:5]   # failed while unbinding the pwrctrl device
        self.assertEqual(lab.undo_plan(completed),
                         ["wifi-rebind-l1", "psoc-timer-restore",
                          "watcher-start", "display-unpark"])

    def test_post_runs_readouts_before_restoring(self):
        post = lab.post_plan(attempt(wifi="L1", beacon=True, alarm_s=120))
        self.assertEqual(post[:3], ["readouts", "resume-ok", "mount-check"])
        self.assertEqual(post[-2:], ["panel-readout", "beacon"])
        self.assertLess(post.index("wifi-rebind-l1"), post.index("display-on"))


class E5Level(unittest.TestCase):
    def test_e4_kept_passed_means_l1_with_a_gate(self):
        self.assertEqual(lab.e5_level(True, {}), ("L1", True))

    def test_first_passing_removal_level(self):
        self.assertEqual(lab.e5_level(False, {"L1": True}), ("L1", False))
        self.assertEqual(lab.e5_level(False, {"L1": False, "L2": True}), ("L2", False))

    def test_no_level_passed(self):
        self.assertIsNone(lab.e5_level(False, {"L1": False, "L2": False}))


if __name__ == "__main__":
    unittest.main()
