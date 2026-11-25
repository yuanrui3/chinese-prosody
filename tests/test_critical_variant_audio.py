from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from data.phonology.annotate import syllable_slots
from src.critical_variant_audio import phrase_timings, prepare


class CriticalVariantAudioTests(unittest.TestCase):
    def test_no_event_and_unobserved_incidence_stay_distinct(self):
        slots = syllable_slots('山水，月出。')
        events = [{'slot_index': i, 'event_index': i, 'status': 'matched',
                   'start_s': start, 'end_s': end}
                  for i, (start, end) in enumerate(((.10, .20), (.21, .35), (.37, .55), (.57, .66)))]
        rows = phrase_timings(slots, events, 'ok', {})
        self.assertEqual([r['elapsed_ms'] for r in rows], [250, 290])
        self.assertEqual([r['final_syllable_ms'] for r in rows], [140, 90])
        self.assertEqual([r['pause_ms'] for r in rows], [None, None])
        self.assertEqual([r['pause_detected'] for r in rows], [False, None])
        self.assertEqual(rows[0]['pause_unavailable'], 'no_assigned_event')
        self.assertEqual(phrase_timings(slots, events, 'ok', {2: 140})[0]['pause_ms'], 140)
        events[2]['status'] = 'substitution'
        rows = phrase_timings(slots, events, 'ok', {2: 110})
        self.assertIsNone(rows[0]['pause_ms'])
        self.assertIsNone(rows[0]['pause_detected'])
        self.assertIsNone(rows[1]['elapsed_ms'])
        self.assertEqual(rows[1]['final_syllable_ms'], 90)

    def test_repeats_clone_input_and_family(self):
        rows = [dict(id=i, family='test', text=t, pinyin=p, source='fixture')
                for i, t, p in [('one', '山水，月出。', 'shan1 shui3 yue4 chu1'),
                                ('two', '水出，月出。', 'shui3 chu1 yue4 chu1')]]
        with TemporaryDirectory() as temp:
            root = Path(temp)
            prepare({'versions': rows}, root)
            families = json.loads((root / 'families.json').read_text())
            readings = json.loads((root / 'readings.json').read_text())
            self.assertEqual(families, {'one': 'test', 'one-repeat': 'test', 'two': 'test'})
            self.assertEqual(readings['one'], readings['one-repeat'])
            self.assertNotEqual(readings['one']['text_sha256'], readings['two']['text_sha256'])
