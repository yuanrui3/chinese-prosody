import unittest

from src.written_tie_audit import layer_profile


class TieProfileTests(unittest.TestCase):
    def test_identifies_where_distinct_inputs_become_equivalent(self):
        model = {
            "names": ["a", "b", "c"],
            "means": [2.0, 0.0, 1.0],
            "scales": [1.0, 2.0, 1.0],
            "weights": [1.0, 0.0, 3.0],
            "observed": [2, 4, 5],
        }
        columns, rows = layer_profile(model, [{"a": None, "b": 3, "c": 2}, {"a": 2, "b": 2, "c": 2}])
        self.assertEqual(columns["a"]["missing_count"], 1)
        self.assertEqual(columns["a"]["raw"], [None, 2.0])
        self.assertEqual(columns["a"]["imputed"], [2.0])
        self.assertEqual(columns["b"]["standardized"], [1.5, 1.0])
        self.assertEqual(columns["b"]["weighted"], [0.0])
        self.assertEqual(rows[0]["weighted"], rows[1]["weighted"])
        self.assertEqual(rows[0]["weighted"], [0.0, 0.0, 3.0])
