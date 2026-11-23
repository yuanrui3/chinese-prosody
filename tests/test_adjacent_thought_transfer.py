import unittest

from src.adjacent_thought_transfer import link_packets


class AdjacencyTests(unittest.TestCase):
    def test_donors_remain_in_section_and_gaps_do_not_create_false_neighbors(self):
        texts = ["東風。", "南雨。", "西雷。", "北露。", "秋水。", "冬雪。", "□。", "春潮。"]
        rows = [dict(work_id="w", id=str(i), section="one", text=t) for i,t in enumerate(texts)]
        rows += [dict(work_id="w", id="8", section="two", text="細浪。")]
        links, key, starts = link_packets(rows)
        self.assertEqual(starts,[("w","0"),("w","8")])
        self.assertEqual(len(links),len(set(r["id"] for r in links)))
        self.assertEqual([r["id"] for r in key],[r["id"] for r in links])
        genuine = [(int(r["prior_id"]),int(r["target_id"])) for r in key if r["authentic"]]
        self.assertCountEqual(genuine,[(0,1),(1,2),(2,3),(3,4),(4,5)])
        controls = [r for r in key if not r["authentic"]]
        self.assertEqual(len(controls),2)
        self.assertTrue(all(int(r["target_id"])-int(r["prior_id"]) >= 3 for r in controls))
        self.assertEqual(link_packets(rows),(links,key,starts))
