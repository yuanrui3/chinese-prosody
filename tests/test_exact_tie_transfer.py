import math
import unittest

from src.exact_tie_transfer import base, make_packets, select_targets


class FullPrecisionScreenTests(unittest.TestCase):
    def test_only_within_work_exact_duplicates_with_intact_predecessors_qualify(self):
        units = ["冬。", "春水。", "夏山。", "秋雲。", "晚鐘。", "江。", "星月。"]
        rows = [
            dict(work_id="a" if i < 5 else "b", section="p", id=str(i), text=t) for i, t in enumerate(units)
        ]
        values = [6, 6, 6, math.nextafter(6.0, 7.0), 5, 5, 6]
        result = select_targets(rows, {base.target_key(r): v for r, v in zip(rows, values)}, set())
        self.assertEqual([r["index"] for r in result["targets"]], [1, 2])
        self.assertEqual(result["eligible"], 5)
        self.assertEqual(result["works_with_ties"], 1)
        packets = make_packets(rows, int(result["mask"], 16))
        self.assertEqual([r["index"] for r in packets["key.json"]], [1, 2])
        self.assertEqual({r["prior"] for r in packets["links.json"]}, {"冬。", "春水。"})
        self.assertNotIn("group", str(packets["editor-packet.json"]))
        # Reusing the predecessor prevents the only pair of equal eligible forecasts.
        screened = select_targets(rows, {base.target_key(r): v for r, v in zip(rows, values)}, {"冬"})
        self.assertEqual(screened["targets"], [])
