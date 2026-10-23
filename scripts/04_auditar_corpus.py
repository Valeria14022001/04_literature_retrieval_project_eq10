"""Auditoría de solo lectura del corpus literario sin normalizar (stdlib).

Ejecutar desde cualquier carpeta: python scripts/04_auditar_corpus.py
Los umbrales generan alertas, nunca eliminan ni reescriben fragmentos.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
from difflib import SequenceMatcher
import hashlib
import html
import itertools
import json
from pathlib import Path
import re
import statistics
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ('fragment_id', 'book_id', 'title', 'author', 'language', 'source',
            'chapter_position', 'position_rel', 'text')


def read_tsv(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f, delimiter='\t')
        fields = reader.fieldnames or []
        if len(fields) != len(set(fields)):
            raise ValueError(f'Columnas repetidas en {path}')
        rows = list(reader)
    if any(None in r or any(v is None for v in r.values()) for r in rows):
        raise ValueError(f'Filas con un número incorrecto de columnas en {path}')
    return fields, rows


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def shingles(tokens, k):
    return {tuple(tokens[i:i+k]) for i in range(len(tokens)-k+1)}


def similar_pairs(rows, k=5, threshold=.8, overlap=.2, min_shared=50):
    """Índice exhaustivo de n-gramas de palabras, sensible a caja y acentos.

    Jaccard detecta similitud global; contención y bloque consecutivo detectan
    fragmentos parcialmente superpuestos. No se calcula similitud semántica.
    """
    tokens = [r.get('text', '').split() for r in rows]
    sets = [shingles(t, k) for t in tokens]
    index = defaultdict(list)
    intersections = Counter()
    for i, current in enumerate(sets):
        for gram in current:
            for j in index[gram]:
                intersections[j, i] += 1
            index[gram].append(i)
    result = []
    for (i, j), shared in sorted(intersections.items()):
        if rows[i].get('text', '') == rows[j].get('text', ''):
            continue
        a, b = len(sets[i]), len(sets[j])
        jac = shared / (a+b-shared)
        containment = shared / min(a, b)
        # Una corrida de m palabras contiene como máximo m-k+1 n-gramas
        # distintos, pero las repeticiones impiden usarlo como filtro seguro.
        match = SequenceMatcher(None, tokens[i], tokens[j], autojunk=False).find_longest_match()
        fraction = match.size / max(1, min(len(tokens[i]), len(tokens[j])))
        if jac >= threshold or (containment >= threshold and shared >= max(1, min_shared-k+1)) or (match.size >= min_shared and fraction >= overlap):
            result.append(dict(fila_a=i+1, fila_b=j+1,
                fragment_id_a=rows[i].get('fragment_id', ''),
                fragment_id_b=rows[j].get('fragment_id', ''),
                book_id_a=rows[i].get('book_id', ''), book_id_b=rows[j].get('book_id', ''),
                jaccard=round(jac, 6), contencion=round(containment, 6),
                palabras_bloque=match.size, fraccion_bloque=round(fraction, 6),
                inicio_palabra_a=match.a, inicio_palabra_b=match.b,
                evidencia=' '.join(tokens[i][match.a:match.a+min(match.size, 60)])))
    return result


def save_csv(path, rows, fields):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run(args):
    before = hashlib.sha256(args.corpus.read_bytes()).hexdigest()
    fields, rows = read_tsv(args.corpus)
    alerts, details, correspondence, coverage = [], [], [], []
    def alert(i, field, issue):
        alerts.append(dict(fila=i+1, fragment_id=rows[i].get('fragment_id', ''),
                           campo=field, alerta=issue))
    source_map = defaultdict(list)
    for path in sorted(args.origen.rglob('*.txt')):
        source_map[path.stem].append(path)
    source_cache = {}
    ids = Counter(r.get('fragment_id', '') for r in rows)
    by_book = defaultdict(list)
    hashes = defaultdict(list)
    for i, row in enumerate(rows):
        text = row.get('text', '')
        words = len(text.split())
        state = 'Aceptable' if args.min_palabras <= words <= args.max_palabras else 'Revisar'
        details.append(dict(fila=i+1, fragment_id=row.get('fragment_id', ''),
                            book_id=row.get('book_id', ''), palabras=words, longitud=state,
                            sha256=sha(text)))
        hashes[sha(text)].append(i)
        for field in REQUIRED:
            if not row.get(field, '').strip():
                alert(i, field, 'Columna ausente' if field not in fields else 'Valor vacío')
        if ids[row.get('fragment_id', '')] > 1:
            alert(i, 'fragment_id', 'Identificador repetido')
        if row.get('n_words', '') and row['n_words'] != str(words):
            alert(i, 'n_words', f'Conteo declarado diferente del calculado: {words}')
        try:
            position = float(row.get('position_rel', ''))
            if not 0 <= position <= 1:
                raise ValueError()
        except ValueError:
            position = None
            alert(i, 'position_rel', 'Posición inválida; se espera número entre 0 y 1')
        if not text.strip():
            alert(i, 'text', 'Texto vacío')
        anomalous = Counter(c for c in text if c == '\ufffd' or
                            (unicodedata.category(c) in ('Cc', 'Cs') and c not in '\n\r\t'))
        if anomalous:
            alert(i, 'text', 'Caracteres anómalos: ' + ', '.join(f'U+{ord(c):04X} ({n})' for c, n in anomalous.items()))
        if re.search(r'Ã.|Â.|â€|ï¿½', text):
            alert(i, 'text', 'Posible error de codificación (heurística)')
        if re.search(r'(?im)^\s*(?:cap[ií]tulo\b|[ií]ndice\s*$|www\.|https?://|p[aá]gina\s+\d)', text):
            alert(i, 'text', 'Posible encabezado o residuo editorial; revisar contexto')
        by_book[row.get('book_id', '')].append((i, position))
        paths = source_map.get(row.get('book_id', ''), [])
        status, start, end, path_name = 'Origen ausente', '', '', ''
        if len(paths) > 1:
            status = 'Origen ambiguo'
        elif len(paths) == 1:
            path = paths[0]
            path_name = str(path)
            if path not in source_cache:
                # newline='' conserva los finales de línea del archivo fuente.
                with path.open(encoding='utf-8-sig', newline='') as f:
                    original = f.read()
                source_cache[path] = (original, list(re.finditer(r'\S+', original)))
            original, spans = source_cache[path]
            start = original.find(text) if text.strip() else -1
            if start >= 0:
                end, status = start+len(text), 'Literal'
            elif text.strip():
                # Vista auxiliar: solo separadores, sin modificar el texto literario.
                joined = ' '.join(m.group() for m in spans)
                target = ' '.join(text.split())
                pos = joined.find(target)
                if pos >= 0 and (pos == 0 or joined[pos-1] == ' ') and (pos+len(target) == len(joined) or joined[pos+len(target)] == ' '):
                    first = joined[:pos].count(' ')
                    start, end = spans[first].start(), spans[first+words-1].end()
                    status = 'Solo diferencias de espacios'
                else:
                    start, status = '', 'No localizado; revisar limpieza o extracción'
            else:
                start, status = '', 'Texto vacío'
        correspondence.append(dict(fila=i+1, fragment_id=row.get('fragment_id', ''),
            archivo_origen=path_name, estado=status, inicio_caracter=start, fin_caracter=end))
    exact = []
    for digest, members in hashes.items():
        for i, j in itertools.combinations(members, 2):
            exact.append(dict(fila_a=i+1, fila_b=j+1, fragment_id_a=rows[i].get('fragment_id', ''),
                              fragment_id_b=rows[j].get('fragment_id', ''), sha256=digest))
    approximate = similar_pairs(rows, args.ngrama, args.similitud, args.solapamiento, args.min_compartidas)
    for book, members in sorted(by_book.items()):
        zones = Counter(min(2, int(pos*3)) for _, pos in members if pos is not None)
        missing = len(members)-sum(zones.values())
        coverage.append(dict(book_id=book, fragmentos=len(members), inicio=zones[0],
            desarrollo=zones[1], final=zones[2], sin_posicion=missing,
            estado='Revisar' if missing or len(zones) < 3 else 'Tres tercios representados'))
        for field in ('title', 'author', 'language', 'source'):
            values = {rows[i].get(field, '').strip() for i, _ in members} - {''}
            if len(values) > 1:
                for i, _ in members:
                    alert(i, field, 'Metadatos inconsistentes dentro de la obra')
    diversity = []
    for field in ('author', 'book_id', 'source', 'language'):
        for value, count in Counter(r.get(field, '') for r in rows).most_common():
            diversity.append(dict(dimension=field, valor=value or '(vacío)', fragmentos=count,
                porcentaje=round(100*count/max(1, len(rows)), 3)))
    lengths = [d['palabras'] for d in details]
    summary = dict(fecha_utc=datetime.now(timezone.utc).isoformat(), corpus=str(args.corpus),
        sha256_corpus=before, fragmentos=len(rows),
        obras=len({r.get('book_id') for r in rows if r.get('book_id')}),
        autores=len({r.get('author') for r in rows if r.get('author')}),
        longitud=dict(minimo=min(lengths, default=0), maximo=max(lengths, default=0),
            media=statistics.mean(lengths) if lengths else 0,
            mediana=statistics.median(lengths) if lengths else 0,
            fuera_objetivo=sum(d['longitud']=='Revisar' for d in details)),
        pares_exactos=len(exact), pares_similares=len(approximate), alertas=len(alerts),
        correspondencia=dict(Counter(r['estado'] for r in correspondence)),
        parametros={k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()})
    if hashlib.sha256(args.corpus.read_bytes()).hexdigest() != before:
        raise RuntimeError('El corpus cambió durante la auditoría')
    args.salida.mkdir(parents=True, exist_ok=True)
    tables = [('fragmentos', details, ['fila','fragment_id','book_id','palabras','longitud','sha256']),
        ('duplicados_exactos', exact, ['fila_a','fila_b','fragment_id_a','fragment_id_b','sha256']),
        ('similares', approximate, ['fila_a','fila_b','fragment_id_a','fragment_id_b','book_id_a','book_id_b','jaccard','contencion','palabras_bloque','fraccion_bloque','inicio_palabra_a','inicio_palabra_b','evidencia']),
        ('alertas', alerts, ['fila','fragment_id','campo','alerta']),
        ('correspondencia', correspondence, ['fila','fragment_id','archivo_origen','estado','inicio_caracter','fin_caracter']),
        ('cobertura', coverage, ['book_id','fragmentos','inicio','desarrollo','final','sin_posicion','estado']),
        ('diversidad', diversity, ['dimension','valor','fragmentos','porcentaje'])]
    for name, table, columns in tables:
        save_csv(args.salida / f'{name}.csv', table, columns)
    (args.salida/'resumen.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    sections = []
    for name, table, columns in tables:
        header = ''.join(f'<th>{html.escape(c)}</th>' for c in columns)
        body = ''.join('<tr>'+''.join(f'<td>{html.escape(str(r[c]))}</td>' for c in columns)+'</tr>' for r in table)
        sections.append(f'<h2>{name} ({len(table)})</h2><p><a href="{name}.csv">Descargar CSV</a></p><div><table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div>')
    histogram = Counter(f'Menos de {args.min_palabras}' if n < args.min_palabras else 'En objetivo' if n <= args.max_palabras else f'Más de {args.max_palabras}' for n in lengths)
    bars = ''.join(f'<p>{html.escape(label)}: {count} <meter min="0" max="{max(1,len(rows))}" value="{count}"></meter></p>' for label,count in histogram.items())
    page = '<!doctype html><html lang="es"><meta charset="utf-8"><title>Auditoría del corpus</title><style>body{font:15px system-ui;margin:36px;color:#183047}div{overflow:auto;max-height:520px}table{border-collapse:collapse;width:100%}td,th{padding:8px;border:1px solid #ccd7df;text-align:left}th{background:#eaf1f7;position:sticky;top:0}meter{width:260px}pre{white-space:pre-wrap}</style><h1>Auditoría del corpus sin normalizar</h1><p>Alertas para revisión humana. No se eliminó ni modificó ningún fragmento. Cobertura por tercios de position_rel: no mide continuidad ni porcentaje de texto cubierto. La similitud es léxica y sensible a caja, acentos y puntuación; no detecta toda paráfrasis. Las diferencias de espacios se comprueban en una vista auxiliar. Índices desde cero; fin exclusivo. Encabezados y caracteres sospechosos requieren interpretación literaria.</p>'+bars+'<pre>'+html.escape(json.dumps(summary, ensure_ascii=False, indent=2))+'</pre>'+''.join(sections)+'</html>'
    (args.salida/'informe.html').write_text(page, encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f'Informe: {args.salida / "informe.html"}')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, default=ROOT/'datos/literature_raw_corpus.tsv')
    parser.add_argument('--origen', type=Path, default=ROOT/'datos/fuentes_epub')
    parser.add_argument('--salida', type=Path, default=ROOT/'auditoria/revision_tecnica')
    parser.add_argument('--min-palabras', type=int, default=700)
    parser.add_argument('--max-palabras', type=int, default=1300)
    parser.add_argument('--ngrama', type=int, default=5)
    parser.add_argument('--similitud', type=float, default=.8)
    parser.add_argument('--solapamiento', type=float, default=.2)
    parser.add_argument('--min-compartidas', type=int, default=50)
    args = parser.parse_args()
    if not (1 <= args.min_palabras <= args.max_palabras and 1 <= args.ngrama <= args.min_compartidas and 0 < args.similitud <= 1 and 0 < args.solapamiento <= 1):
        parser.error('Umbrales inválidos')
    if args.salida.resolve() == args.origen.resolve() or args.corpus.resolve().parent == args.salida.resolve():
        parser.error('Usa una carpeta de salida separada del corpus y del origen')
    run(args)


if __name__ == '__main__':
    main()
