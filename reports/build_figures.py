"""Build the final report figures from the checked Stage 5 release tables."""

import argparse
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory


REPORTS = Path(__file__).resolve().parent
CONTROLS = (
    ('Opposed 平仄 at annotated paired ends', 'Stratified tone reassignment',
     'Paired-end tone opposition / tone reassignment', 'parallel_end_pz_opposition', 'tone_stratified'),
    ('Paired-side length similarity', 'Whole-clause reorder',
     'Paired-side length similarity / clause reorder', 'parallel_length_similarity', 'clause_order'),
    ('Opposed 平仄 at annotated paired ends', 'Within-clause syllable shuffle',
     'Paired-end tone opposition / syllable shuffle', 'parallel_end_pz_opposition', 'within_clause'),
    ('Alternation across successive clause ends', 'Stratified tone reassignment',
     'Clause-end tone alternation / tone reassignment', 'clause_end_pz_alternation', 'tone_stratified'),
)
AGREEMENT = (
    ('Mean clause length and mean articulation time', 'Mean clause length / time', 'clause_mean_slots'),
    ('Clause-length SD and clause articulation-time SD', 'Clause-length SD / time SD', 'clause_sd_slots'),
    ('Clause-length nPVI and articulation-time nPVI', 'Clause-length nPVI / timing nPVI', 'clause_npvi'),
    ('Internal punctuation density and 150 ms quiet-gap candidate density',
     'Punctuation density / quiet-gap density', 'internal_boundary_rate'),
    ('Historical 平 share by count and by articulation duration',
     'Historical level-tone share by count / time', 'ping_share'),
    ('Syllable-level 平仄 alternation and adjacent absolute pitch reset',
     'Syllable-tone alternation / pitch reset', 'syllable_pz_alternation'),
    ('Even-slot 平仄 alternation and late-F0 differences',
     'Even-slot tone alternation / late pitch difference', 'foot_pz_alternation'),
    ('Clause-end 平仄 alternation and late-F0 differences',
     'Clause-end tone alternation / late pitch difference', 'clause_end_pz_alternation'),
    ('Adjacent reconstructed initial recurrence and draft Mandarin onset recurrence',
     'Reconstructed initial / draft onset recurrence', 'adjacent_initial_repeat'),
    ('Adjacent reconstructed final recurrence and draft Mandarin final recurrence',
     'Reconstructed final / draft final recurrence', 'adjacent_final_repeat'),
)


def table(markdown, heading):
    lines = markdown.splitlines()
    first = next(index for index, line in enumerate(lines) if line.startswith(f'| {heading} |'))
    for line in lines[first + 2:]:
        if not line.startswith('|'):
            break
        yield tuple(cell.strip() for cell in line.strip('|').split('|'))


def from_checkpoint(markdown):
    controls = {(name, null): (int(n), float(effect), float(adjusted))
                for name, null, n, effect, _, adjusted in table(markdown, '《廣韻》 descriptor')}
    agreement = {name: (int(n), float(rho.replace('−', '-')))
                 for name, n, rho in table(markdown, 'Text measure and acoustic counterpart')}
    return (
        [(label, *controls[name, null]) for name, null, label, _, _ in CONTROLS],
        [(label, *agreement[name]) for name, label, _ in AGREEMENT],
    )


def from_validation(value):
    controls = {(row['metric'], row['null']): row
                for row in value['tiers']['guangyun']['shuffled_controls'] if row['status'] == 'tested'}
    comparisons = value['audio']['comparisons']
    return (
        [(label, controls[key, null]['passages'], controls[key, null]['real_minus_control'],
          controls[key, null]['p_holm']) for _, _, label, key, null in CONTROLS],
        [(label, comparisons[key]['matched']['passages'], comparisons[key]['matched']['rho'])
         for _, label, key in AGREEMENT],
    )


def gnuplot_string(value):
    return json.dumps(value, ensure_ascii=False)


def style(destination, height, rows, xlabel):
    labels = ', '.join(f'{gnuplot_string(f"{label} (n={n})")} {index}'
                       for index, (label, n, *_) in enumerate(rows, 1))
    return f'''
set terminal svg size 1140,{height} background rgb '#ffffff' font 'Arial,17'
set output {gnuplot_string(str(destination))}
set encoding utf8
set lmargin at screen 0.44
set rmargin at screen 0.91
set tmargin 1.5
set bmargin 4
set border 1 lc rgb '#667781'
set grid xtics back lc rgb '#dbe5e9'
set xzeroaxis dt 2 lc rgb '#667781'
set xtics nomirror textcolor rgb '#253945'
set ytics ({labels}) scale 0 textcolor rgb '#253945'
set yrange [{len(rows) + 0.6}:0.4]
set xlabel {gnuplot_string(xlabel)} textcolor rgb '#253945'
unset key
'''


def plot(destination, rows, agreement=False):
    if agreement:
        settings = style(destination, 485, rows, 'Spearman rank correlation')
        settings += 'set xrange [-1.17:1.17]\nset xtics -1,0.5,1\n'
        columns = (f'{index} {rho:.6f} {gnuplot_string(f"{rho:.3f}")}'
                   for index, (_, _, rho) in enumerate(rows, 1))
        annotations = "$Data using ($2 >= 0 ? $2 : 1/0):1:3 with labels left offset char 0.6,0 tc rgb '#253945', \\\n       $Data using ($2 < 0 ? $2 : 1/0):1:3 with labels right offset char -0.6,0 tc rgb '#253945'"
    else:
        settings = style(destination, 258, rows, 'Observed minus shuffled mean (percentage points)')
        settings += 'set xrange [0:71]\nset xtics 0,10,60\n'
        columns = (f'{index} {100 * effect:.6f} {gnuplot_string(f"{100 * effect:+.1f} pp, p adj {p:.3f}")}'
                   for index, (_, _, effect, p) in enumerate(rows, 1))
        annotations = "$Data using 2:1:3 with labels left offset char 0.6,0 tc rgb '#253945'"
    data = '\n'.join(columns)
    script = f"""{settings}
$Data << EOD
{data}
EOD
plot $Data using (0):1:2:(0) with vectors nohead lw 3 lc rgb '#79aaa3', \\
     $Data using 2:1 with points pt 7 ps 1.1 lc rgb '#12685e', \\
     {annotations}
"""
    subprocess.run(['gnuplot'], input=script, text=True, check=True)
    svg = destination.read_text(encoding='utf-8').rstrip()
    destination.write_text('\n'.join(line.rstrip() for line in svg.splitlines()) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validation', type=Path, help='Use the full Stage 5 validation.json on Gilbreth')
    parser.add_argument('--output', type=Path, default=REPORTS / 'figures')
    args = parser.parse_args()
    if args.validation is None:
        controls, agreement = from_checkpoint((REPORTS / 'stage-5.md').read_text(encoding='utf-8'))
    else:
        controls, agreement = from_validation(json.loads(args.validation.read_text(encoding='utf-8')))
    args.output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=args.output) as staging:
        destination = Path(staging)
        effect_file = destination / 'shuffled-controls.svg'
        agreement_file = destination / 'text-audio-agreement.svg'
        plot(effect_file, controls)
        plot(agreement_file, agreement, agreement=True)
        for figure in (effect_file, agreement_file):
            figure.replace(args.output / figure.name)


if __name__ == '__main__':
    main()
