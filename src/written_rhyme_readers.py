"""Join the two anonymous written readings to the sealed corpus on Gilbreth."""

import argparse
from collections import Counter
from csv import reader
from pathlib import Path
from statistics import fmean

from .quantitative_ending_functions import digest, read
from .yu_review_baseline import save_sealed


def verify_inputs(inputs):
    for name, expected in read(inputs / 'source-seal.json').items():
        if digest(inputs / name) != expected:
            raise ValueError(f'Changed source packet file: {name}')


def read_judgments(path, packet, key):
    result = {}
    with path.open(encoding='utf-8-sig', newline='') as stream:
        for line in reader(stream, delimiter='\t', quoting=3):
            if len(line) != 4:
                raise ValueError(f'Expected four fields at row {len(result) + 1}')
            blind, grade, quote, reason = line
            if (blind in result or blind not in packet or grade not in tuple('1234567')
                    or not quote.strip() or quote not in packet[blind]['text'] or not reason.strip()):
                raise ValueError(f'Invalid or unanchored editorial response for {blind!r}')
            result[blind] = dict(id=key[blind], score=int(grade), quote=quote, reason=reason)
    if result.keys() != packet.keys():
        raise ValueError('Ratings must cover all and only the anonymous targets')
    return result


def join(run):
    inputs = run / 'inputs'
    verify_inputs(inputs)
    key = read(inputs / 'reader-key.json')
    packet = {r['blind_id']: r for r in read(inputs / 'reading.json')}
    targets = {r['id']: r for r in read(inputs / 'corpus.json') if r['target']}
    if (packet.keys() != key.keys() or len(set(key.values())) != len(key)
            or set(key.values()) != targets.keys()
            or any(packet[b]['text'] != targets[i]['text'] for b, i in key.items())):
        raise ValueError('Masked packet differs from the original target roster')
    forecasts = run / 'results/forecasts.json'
    if read(forecasts)['hashes']['corpus'] != digest(inputs / 'corpus.json'):
        raise ValueError('Frozen forecasts and reader corpus differ')
    paths = [(Path((run / 'readers' / f'{role}.path').read_text().strip()) / 'ratings.tsv')
             for role in ('primary', 'second')]
    if paths[0].resolve() == paths[1].resolve():
        raise ValueError('The two separate sessions must submit independent files')
    judgments = [read_judgments(path, packet, key) for path in paths]
    for name, rated in zip(('ratings.json', 'ratings-second.json'), judgments):
        save_sealed(inputs / name, [rated[b] for b in sorted(packet)])
    by_genre = {}
    for group in ('all', 'fu', 'prose'):
        pairs = [(judgments[0][b]['score'], judgments[1][b]['score']) for b, i in key.items()
                 if group == 'all' or targets[i]['genre'] == group]
        differences = [abs(a - b) for a, b in pairs]
        by_genre[group] = dict(n=len(pairs), exact=differences.count(0),
                               within_one=sum(d <= 1 for d in differences),
                               mean_absolute_difference=fmean(differences),
                               primary_minus_second=fmean(a-b for a, b in pairs),
                               score_pairs=dict(Counter(f'{a},{b}' for a, b in pairs)))
    save_sealed(run / 'results/reading-agreement.json',
                dict(agreement=by_genre, forecasts_sha256=digest(forecasts),
                     packet_sha256=digest(inputs / 'reading.json'), reader_sha256=[digest(path) for path in paths]))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    join(parser.parse_args().run)
