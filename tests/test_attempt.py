# SPDX-License-Identifier: GPL-2.0-only
"""Attempt record: schema, freshness and lab identity."""

import unittest

from labtool import lab


class AttemptRecord(unittest.TestCase):
    def test_round_trip(self):
        a = lab.Attempt(bootid="b1", ts=100.0, rung="E5", wifi="L1",
                        display="park", alarm_s=120, beacon=True,
                        kernelrelease="k", candidate="00-debug", build="7")
        self.assertEqual(lab.Attempt.from_json(a.to_json()), a)
        self.assertEqual(a.key, ("b1", 100.0))

    def test_rejects_unknown_values_and_fields(self):
        with self.assertRaises(lab.LabError):
            lab.Attempt(bootid="b", ts=0, rung="E9")
        with self.assertRaises(lab.LabError):
            lab.Attempt(bootid="b", ts=0, rung="E2", wifi="L3")
        with self.assertRaises(lab.LabError):
            lab.Attempt.from_json('{"bootid": "b", "ts": 0, "rung": "E2", "extra": 1}')

    def test_freshness(self):
        a = lab.Attempt(bootid="b1", ts=1000.0, rung="E2")
        self.assertTrue(a.is_fresh("b1", 1000.0 + 599))
        self.assertFalse(a.is_fresh("b1", 1000.0 + 601))
        self.assertFalse(a.is_fresh("b2", 1001.0))
        self.assertFalse(a.is_fresh("b1", 999.0))

    def test_lab_identity_from_cmdline(self):
        cmd = ("root=PARTLABEL=linux panic=10 pm_debug_messages "
               "erhai_lab.candidate=00-debug erhai_lab.build=7")
        self.assertEqual(lab.lab_identity(cmd), ("00-debug", "7"))
        self.assertEqual(lab.lab_identity("root=PARTLABEL=linux panic=30"), ("", ""))


if __name__ == "__main__":
    unittest.main()
