from hashlib import sha256
from importlib.util import find_spec
from random import Random
import unittest

if find_spec('numpy'):
    from src.quantitative_editorial_audio import VOICES, evaluate, paired_rows, shuffle_acoustics


def corpus():
    context = {'rows': []}
    audio = {'lines': {}}
    for work in ('first', 'second'):
        for i, line in enumerate('甲乙丙丁戊己'):
            context['rows'].append({'work_id': work, 'id': line, 'text': line, 'editorial_score': i + 2,
                                    'predictions': {'context': {'raw': 4.5}}})
            takes = {}
            for j, voice in enumerate(VOICES):
                site = {'ordinal': 1, 'exclusion': None, 'pause_ms': 10 * (i + 1) + j,
                        'pre_duration_s': (i + 1) * .05 + j * .01, 'context_duration_s': .15}
                sites = [site]
                if j:
                    sites.append({**site, 'ordinal': 2, 'pause_ms': 800})
                # Exclude this entire line in both voices when just one voice cannot support any shared site.
                elif i == 5:
                    sites = []
                takes[voice] = {'junctions': sites}
            audio['lines'][work + line] = {'work_id': work, 'id': line, 'voices': takes,
                                           'candidate_junctions': [1, 2], 'text_sha256': sha256(line.encode()).hexdigest()}
    return audio, context


@unittest.skipUnless(find_spec('numpy'), 'NumPy is part of the quantitative scoring environment')
class EditorialAudioTests(unittest.TestCase):
    def test_common_sites_and_training_label_isolation(self):
        audio, context = corpus()
        report = evaluate(audio, context, draws=3)
        self.assertTrue(all(r['shared_ordinals'] == [1] and r['id'] != '己' for r in report['predictions']))
        self.assertEqual(len(report['folds']), 4)
        for fold in report['folds']:
            self.assertEqual((fold['train_lines'], fold['test_lines']), (5, 5))
            self.assertNotIn(fold['work_id'], fold['training_works'])
        for row in context['rows']:
            if row['work_id'] == 'first':
                row['editorial_score'] = 1
        changed = evaluate(audio, context, draws=0)
        for a, b in zip(report['predictions'], changed['predictions']):
            if a['work_id'] == 'first':
                self.assertEqual(a['forecast'], b['forecast'])

    def test_shuffle_preserves_work_voice_pairing_and_targets(self):
        audio, context = corpus()
        rows, _ = paired_rows(audio, context, ())
        original = {(r['work_id'], r['id'], r['voice']): r for r in rows}
        # Fingerprint each donor line to make crossing either a work or a voice detectable.
        for row in rows:
            row['pause'] += 100 if row['work_id'] == 'first' else 0
        shuffled = shuffle_acoustics(rows, Random(17))
        self.assertEqual(shuffled, shuffle_acoustics(rows, Random(17)))
        changed = 0
        for row in shuffled:
            own = original[row['work_id'], row['id'], row['voice']]
            self.assertEqual((row['label'], row['context_score']), (own['label'], own['context_score']))
            donors = [r for r in rows if r['voice'] == row['voice'] and r['pause'] == row['pause']]
            self.assertEqual(len(donors), 1)
            donor = donors[0]
            self.assertEqual(donor['work_id'], row['work_id'])
            self.assertEqual(donor['duration'], row['duration'])
            other = next(v for v in VOICES if v != row['voice'])
            mate = next(r for r in shuffled if (r['work_id'], r['id'], r['voice']) == (row['work_id'], row['id'], other))
            self.assertEqual(mate['pause'], original[donor['work_id'], donor['id'], other]['pause'])
            changed += int(row['id'] != donor['id'])
        self.assertGreater(changed, 0)


if __name__ == '__main__':
    unittest.main()
