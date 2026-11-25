import unittest
from src.reversal_challenge import FRESH
from src.reversal_detector import calibrated
from src.reversal_sources import exact
from src.reversal_evaluate import confusion
from src.semicolon_turn_controls import ITEMS


class ReversalTransferTests(unittest.TestCase):
    def test_literal_matched_endings_and_new_stems(self):
        self.assertFalse({p for p,_,_ in FRESH} & {p for p,_,_ in ITEMS})
        self.assertEqual(len(set(p for p,_,_ in FRESH)),16)
        for stem,a,b in FRESH:
            self.assertNotEqual(a,b)
            self.assertTrue(all(exact(stem+x+"。") and len(x)==4 for x in (a,b)))
        self.assertFalse(exact("昔聞，忽來；今察其跡，未能信也。"))

    def test_development_threshold_and_uncertain_semantic_truth(self):
        dev={f"D{i}{c}":{"margin":v} for i in range(len(ITEMS)) for c,v in (("C",-1),("R",2))}
        self.assertEqual(calibrated(dev),0.)
        self.assertEqual(confusion({"a":True,"b":None},{"a":True,"b":False})["n"],1)
