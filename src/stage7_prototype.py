"""Score the reviewed text with the archived written 音律美 model on Gilbreth."""


def sentence_rows(report):
    """Project document-level reviews onto the original punctuation-ended sentences."""
    rows = []
    for paragraph in report['paragraphs']:
        clauses = paragraph['clauses']
        first = 0
        for i, clause in enumerate(clauses):
            marks = clause['slots'][-1]['marks_after']
            if i + 1 < len(clauses) and not any(c in '。！？.!?' for c in marks):
                continue
            start, end = clauses[first]['start'], clause['end']
            text = report['text'][start:end]
            reviews = []
            for group in clauses[first:i + 1]:
                for slot in group['slots']:
                    for tier in report['reference']['historical']:
                        reading = slot['readings'].get(tier, {})
                        chosen = reading.get('selected')
                        if chosen is None:
                            continue
                        selector = {k: chosen[k] for k in ('id', 'lookup_char') if k in chosen}
                        reviews.append({**reading['evidence'], 'tier': tier, 'match': selector,
                                        'anchor': text, 'offset': slot['offset'] - start, 'char': slot['char']})
            rows.append({'id': f'S{len(rows) + 1:03}', 'work_id': report['passage_id'],
                         'section': str(paragraph['paragraph_index'] + 1), 'text': text,
                         'start': start, 'end': end, 'historical_readings': reviews})
            first = i + 1
    return rows


def score_prototype(root, report):
    from src import quantitative_ending_functions as frozen

    archive = root / 'results/grammatical-training-expansion-20261122'
    rows = sentence_rows(report)
    scores, hashes = frozen.model(root, archive, rows)
    return {
        'target': 'Written 音律美, frozen editorial 1–7 estimate',
        'model_sha256': frozen.prev.MODEL_SHA,
        'lexicon_sha256': hashes,
        'sentences': [
            {**{k: row[k] for k in ('id', 'section', 'text', 'start', 'end')},
             'score': None if frozen.prev.incomplete(row) else scores[(row['work_id'], row['id'])],
             'reviewed_historical_readings': len(row['historical_readings'])}
            for row in rows
        ],
    }
