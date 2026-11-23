import json
import unittest

from src.ending_function_metrics import agreement, study


def row(work, score, current=6.0):
    return {'work_id': work, 'score': score, 'current': current}


class EndingFunctionTests(unittest.TestCase):
    def test_agreement_includes_every_category_and_abstains_on_disagreement(self):
        result = agreement(['argument', 'list', 'mixed', 'uncertain'], ['argument', 'list', 'list', 'uncertain'])
        self.assertEqual(result['roles'], ['argument', 'list', None, None])
        self.assertEqual(result['matrix']['mixed']['list'], 1)
        self.assertEqual(result['exact'], 3)
        self.assertEqual(result['agreed_pure_fraction'], 0.5)
        self.assertAlmostEqual(result['kappa'], 2 / 3)
        self.assertIsNone(agreement(['list'], ['list'])['kappa'])
        self.assertIsNone(agreement([], [])['observed_agreement'])

    def test_equal_work_weight_and_separate_comparison_pools(self):
        rows = [row('A', 7), row('A', 6), row('A', 6), row('B', 7), row('B', 6), row('B', 7, 7)]
        roles = ['argument', 'list', 'list', 'list', 'argument', 'argument']
        result = study(rows, roles)
        primary = result['primary']
        self.assertEqual(primary['informative_works'], ['A', 'B'])
        self.assertEqual((primary['argument_7_pairs'], primary['list_7_pairs']), (2, 1))
        self.assertEqual(primary['methods']['always6']['macro'], 0.5)
        self.assertEqual(primary['methods']['function_only']['macro'], 0.5)
        self.assertAlmostEqual(primary['methods']['function_only']['within_pooled'], 2 / 3)
        self.assertEqual(primary['pooled_all']['pairs'], 5)
        self.assertEqual(primary['methods']['function_only']['pooled_all'], 0.8)
        self.assertEqual(result['ordinary']['within_pairs'], 4)
        self.assertEqual(result['ordinary']['same_role_pairs'], 1)

    def test_lower_scores_and_abstentions_remain_in_all_endpoint_error(self):
        rows = [row('A', 5, 6.5), row('B', 7, 7), row('B', 6, 6.6)]
        result = study(rows, [None, 'argument', 'list'])
        all_error = result['error']['all']['methods']['augmented']
        self.assertEqual(all_error['threshold'], {'tp': 1, 'fp': 1, 'tn': 1, 'fn': 0})
        self.assertEqual(all_error['threshold_6_7'], {'tp': 1, 'fp': 0, 'tn': 1, 'fn': 0})
        self.assertAlmostEqual(all_error['mae'], (1.5 + 0.35) / 3)
        self.assertAlmostEqual(all_error['macro_mae'], (1.5 + 0.175) / 2)
        self.assertEqual(result['error']['pure']['n'], 2)
        self.assertEqual(result['scores_by_role']['abstain'], {5: 1})
        self.assertNotIn('function_only', result['error']['pure']['methods'])

    def test_absent_within_work_comparisons_are_undefined(self):
        r = study([row('A', 6), row('B', 7)], ['list', 'argument'], shuffle=True)
        self.assertEqual(r['primary']['pooled_all']['pairs'], 1)
        self.assertIsNone(r['primary']['methods']['current']['macro'])
        self.assertEqual(r['permutation']['draws'], 0)
        self.assertIsNone(r['permutation']['p_upper'])
        json.dumps(study([], [], shuffle=True), allow_nan=False)

    def test_permutation_keeps_original_pairs_and_excludes_lower_scores(self):
        rows = [row('A', 7), row('A', 6), row('A', 5), row('A', 6, 7)]
        roles = ['argument', 'list', 'argument', 'uncertain']
        first = study(rows, roles, shuffle=True)['permutation']
        short = study(rows[:2], roles[:2], shuffle=True)['permutation']
        self.assertEqual(first, short)
        self.assertEqual(first['draws'], 999)
        self.assertEqual(first['observed_gain'], 0.5)
        self.assertLess(420, first['at_least_observed'])
        self.assertLess(first['at_least_observed'], 580)
        self.assertEqual(first['p_upper'], (first['at_least_observed'] + 1) / 1000)


class EndingSourceChecks(unittest.TestCase):
    def test_internal_closure_reserved_unit_and_masked_editorial_packet(self):
        from src.quantitative_ending_functions import endpoints, packets

        rows = [
            dict(work_id="work", section="p", id="a", text="春風，秋雨，冬雪。"),
            dict(work_id="work", section="p", id="b", text="山深，林遠，行難。"),
        ]
        def candidate(ident, previous, ending):
            return dict(work_id="work", section="p", id=ident, quote=ending,
                        prior_quotes=[dict(id=ident,quote=q) for q in previous])
        all_candidates = [
            candidate("a", ("春", "風"), "秋雨"),
            candidate("a", ("春風", "秋雨"), "冬雪"),
            candidate("b", ("山深", "林遠"), "行難"),
        ]
        eligible, omitted = endpoints(rows, all_candidates, [rows[1]])
        self.assertEqual([e["quote"] for e in eligible], ["冬雪"])
        self.assertEqual(len(omitted), 2)
        masked = packets(rows, eligible)
        editorial = masked["packet.json"]
        self.assertEqual([r["text"] for r in editorial], [r["text"] for r in rows])
        self.assertTrue(all(set(r) == {"work_id","id","section","text","incomplete"} for r in editorial))
        self.assertEqual(masked["role-packet.json"]["targets"], [{"id":editorial[0]["id"],"quote":"冬雪"}])
