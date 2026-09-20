"""Physical interval/energy checks independent of the RTL fixture comparison."""
import unittest

from frame_length_reference import (CAPTURE_TRUNCATED, DETECTOR_TIMEOUT,
                                    DIGITAL_ZERO, START_UNCONFIRMED,
                                    reference_digital_zero)


class FrameReferenceTests(unittest.TestCase):
    def reference(self, values, gap=4, maximum=1048576):
        return reference_digital_zero(values, [0] * len(values), gap_min=gap, max_burst=maximum)

    def test_confirmed_exact_support(self):
        records = self.reference([0] * 4 + [3] * 64 + [0] * 4)
        self.assertEqual(len(records), 1)
        self.assertEqual((records[0]["start_sample"], records[0]["end_sample"],
                          records[0]["length_samples"], records[0]["energy"],
                          records[0]["rms_q16"], records[0]["flags"]),
                         (4, 68, 64, 576, 3 * 65536, DIGITAL_ZERO))

    def test_short_zeros_contribute_to_rms_length(self):
        record = self.reference([0] * 4 + [4] + [0] * 3 + [4] + [0] * 4)[0]
        self.assertEqual(record["length_samples"], 5)
        self.assertEqual(record["energy"], 32)
        self.assertLess(record["rms"], 4)

    def test_exact_gap_separates(self):
        records = self.reference([0] * 4 + [3] + [0] * 4 + [4] + [0] * 4)
        self.assertEqual([r["length_samples"] for r in records], [1, 1])
        self.assertEqual([r["flags"] for r in records], [DIGITAL_ZERO] * 2)

    def test_truncated_zeros_use_observed_range(self):
        record = self.reference([3] * 2 + [0] * 3)[0]
        self.assertEqual(record["end_sample"], 5)
        self.assertEqual(record["energy"], 18)
        self.assertEqual(record["flags"], DIGITAL_ZERO | START_UNCONFIRMED | CAPTURE_TRUNCATED)

    def test_maximum_segments_cover_samples(self):
        records = self.reference([3] * 10, maximum=3)
        self.assertEqual([(r["start_sample"], r["end_sample"]) for r in records],
                         [(0, 3), (3, 6), (6, 9), (9, 10)])
        self.assertEqual(sum(r["energy"] for r in records), 90)
        self.assertTrue(all(r["flags"] & DETECTOR_TIMEOUT for r in records[:-1]))
        self.assertTrue(records[-1]["flags"] & CAPTURE_TRUNCATED)

    def test_force_tail_zero_segments_are_explicit(self):
        records = self.reference([1] + [0] * 4, maximum=1)
        self.assertEqual([r["energy"] for r in records], [1, 0, 0, 0])
        self.assertTrue(all(r["flags"] & DETECTOR_TIMEOUT for r in records))
        self.assertTrue(all(r["length_samples"] == 1 for r in records))

    def test_gap_confirmation_wins_on_max_boundary(self):
        record = self.reference([0] * 4 + [3] * 2 + [0] * 4, maximum=6)[0]
        self.assertEqual((record["length_samples"], record["flags"]), (2, DIGITAL_ZERO))

    def test_full_scale_and_offset(self):
        records = reference_digital_zero([0, -32768, 0], [0, -32768, 0],
                                         gap_min=1, start_index=2**40)
        self.assertEqual(records[0]["energy"], 2**31)
        self.assertEqual(records[0]["start_sample"], 2**40 + 1)
        self.assertEqual(records[0]["length_samples"], 1)

    def test_empty_and_zero(self):
        self.assertEqual(self.reference([]), [])
        self.assertEqual(self.reference([0] * 100), [])


if __name__ == "__main__":
    unittest.main()
