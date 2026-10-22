"""Revisión reproducible de 30 casos pendientes, sin modificar las entradas."""
import csv
from collections import Counter, defaultdict
from difflib import SequenceMatcher, HtmlDiff
import html
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'datos/auditoria'


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f, delimiter='\t' if path.suffix == '.tsv' else ','))


def main():
    spec = importlib.util.spec_from_file_location('segmentacion', ROOT/'scripts/02_limpiar_segmentar.py')
    seg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seg)
    corpus = read(ROOT/'datos/literature_raw_corpus.tsv')
    pending = read(OUT/'correspondencia.csv')
    groups = defaultdict(list)
    for row in pending:
        if row['estado'].startswith('No localizado'):
            item = corpus[int(row['fila'])-1]
            groups[item['book_id']].append((row, item))
    # Alternar obras ordenadas; repartir selecciones dentro de cada obra.
    selected = []
    for level in range(max(map(len, groups.values()), default=0)):
        for book in sorted(groups):
            if level < len(groups[book]) and len(selected) < 30:
                selected.append(groups[book][level])
    results, sections = [], []
    for meta, row in selected:
        path = Path(meta['archivo_origen'])
        source = path.read_text(encoding='utf-8-sig')
        spans = list(re.finditer(r'\S+', source))
        words = [m.group() for m in spans]
        target = row['text'].split()
        width = 8
        starts = [i for i in range(len(words)-width+1) if words[i:i+width] == target[:width]]
        ends = [i+width for i in range(len(words)-width+1) if words[i:i+width] == target[-width:]]
        candidates = [(a,b) for a in starts for b in ends if a < b and abs(b-a-len(target)) < len(target)*.5]
        base = dict(fragment_id=row['fragment_id'], book_id=row['book_id'], fuente=str(path),
                    inicios_ancla=len(starts), finales_ancla=len(ends))
        method = 'anclas de extremos'
        if len(candidates) != 1:
            blocks = [m for m in SequenceMatcher(None, words, target, autojunk=False).get_matching_blocks() if m.size >= 8]
            if not blocks:
                results.append(dict(base, estado='Revisar: anclas ausentes o ambiguas'))
                continue
            a = max(0, blocks[0].a-blocks[0].b)
            last = blocks[-1]
            b = min(len(words), last.a+last.size+len(target)-last.b-last.size)
            candidates = [(a,b)]
            method = 'alineación auxiliar; límites estimados'
        a,b = candidates[0]
        passage = source[spans[a].start():spans[b-1].end()]
        changes = []
        for tag,i,j,k,l in SequenceMatcher(None, words[a:b], target, autojunk=False).get_opcodes():
            if tag != 'equal':
                changes.append(dict(tipo=tag, fuente=' '.join(words[a+i:a+j]), corpus=' '.join(target[k:l])))
        # Reproducción del pipeline actual: evidencia adicional, no validación
        # independiente de que las reglas sean literariamente apropiadas.
        cleaned = seg.quitar_titulo_repetido(seg.limpiar_texto(source), row['title'])
        _, merged = seg.segmentar_libro(cleaned, 700, 1300, 1000)
        regenerated = [seg.compactar_para_tsv(seg.quitar_cabecera_fragmento('\n\n'.join(p['texto'] for p in group))) for group in merged]
        reproduced = row['text'] in regenerated
        results.append(dict(base, estado='Comparado', metodo=method, inicio=spans[a].start(),
            fin=spans[b-1].end(), reproducido_pipeline=reproduced, diferencias=changes))
        diff = HtmlDiff(wrapcolumn=100).make_table(passage.splitlines(), row['text'].splitlines(),
            fromdesc='Pasaje fuente', todesc='Fragmento del corpus', context=True, numlines=2)
        sections.append('<h2>'+html.escape(row['fragment_id']+' — '+row['title'])+'</h2><pre>'+html.escape(json.dumps(results[-1], ensure_ascii=False, indent=2))+'</pre>'+diff)
    (OUT/'revision_30.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT/'revision_30.html').write_text('<!doctype html><html lang="es"><meta charset="utf-8"><title>Revisión de 30 fragmentos</title><style>body{font:15px system-ui;margin:25px}table{font:12px monospace;max-width:100%}td{vertical-align:top}.diff_add{background:#bcf0c5}.diff_sub{background:#ffc5c5}.diff_chg{background:#ffeb9a}pre{white-space:pre-wrap}</style><h1>Muestra de correspondencia: 30 casos pendientes</h1><p>Muestra determinista por obra, no aleatoria. Fuente y corpus intactos. Anclas de ocho palabras al inicio y final; intervalo único. Reproducir el pipeline no certifica por sí solo su corrección literaria. Diferencias de espacios quedan visibles en las tablas.</p>'+''.join(sections)+'</html>', encoding='utf-8')
    print(json.dumps(dict(casos=len(results), obras=len({r['book_id'] for r in results}),
        estados=dict(Counter(r['estado'] for r in results)),
        reproducidos=sum(r.get('reproducido_pipeline', False) for r in results)), ensure_ascii=False))


if __name__ == '__main__':
    main()
