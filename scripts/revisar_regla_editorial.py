"""Compara la regla anterior y la corregida sin regenerar el corpus."""
import csv
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'datos/auditoria/regla_editorial'


def main():
    spec = importlib.util.spec_from_file_location('segmentacion', ROOT/'scripts/02_limpiar_segmentar.py')
    seg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seg)
    def anterior(line):
        normal = seg.quitar_acentos(line.strip()).lower()
        # Única diferencia histórica: búsqueda de estas subcadenas en
        # cualquier posición de una línea de hasta 25 palabras.
        return seg.es_linea_basura(line) or (len(line.split()) <= 25 and
            any(word in normal for word in ('correccion', 'transcripcion')))
    inputs = sorted((ROOT/'textos_extraidos').rglob('*.txt'))
    protected = inputs + list((ROOT/'datos').rglob('*.tsv'))
    before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    report = []
    scanned = Counter()
    for path in inputs:
        source = path.read_text(encoding='utf-8-sig')
        prepared = seg.reparar_guiones_y_espacios(seg.cortar_finales_editoriales(source))
        for stage, text in [('fuente', source), ('entrada_real_del_filtro', prepared)]:
            lines = text.splitlines()
            scanned[stage] += len(lines)
            for i, line in enumerate(lines):
                old, new = anterior(line), seg.es_linea_basura(line)
                if old or new:
                    report.append(dict(etapa=stage, archivo=str(path.relative_to(ROOT)),
                        linea=i+1, antes=old, despues=new,
                        cambio='Conservar ahora' if old and not new else 'Sin cambio', texto=line,
                        anterior=lines[i-1] if i else '', siguiente=lines[i+1] if i+1<len(lines) else ''))
    # Regresión: todas las menciones narrativas recuperadas deben sobrevivir.
    recovered = [r for r in report if r['cambio']=='Conservar ahora']
    assert recovered
    for row in recovered:
        assert not seg.es_linea_basura(row['texto'])
        assert row['texto'].strip() in seg.limpiar_lineas_basura(row['texto'])
    for label in ('Corrección: Ana Pérez', 'Transcripción: Juan López',
                  'Corrección de estilo: Ana Pérez', 'Fuente: Wikisource',
                  'Libro descargado en www.elejandria.com'):
        assert seg.es_linea_basura(label), label
    for sentence in ('La corrección de su falta era necesaria.',
                     'Entonces comenzaré la transcripción.',
                     '¿Debería aceptar las correcciones?', 'Corrección sin castigo.',
                     'Una transcripción: eso era lo que necesitaba.', 'Corrección:'):
        assert not seg.es_linea_basura(sentence), sentence
    assert (ROOT/'02_limpiar_segmentar.py').read_bytes() == (ROOT/'scripts/02_limpiar_segmentar.py').read_bytes()
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==digest for p,digest in before.items())
    OUT.mkdir(parents=True, exist_ok=True)
    columns = list(report[0])
    for name, rows in [('comparacion_completa', report), ('lineas_recuperadas', recovered)]:
        with (OUT/f'{name}.csv').open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
    summary = dict(archivos=len(inputs), lineas_examinadas=dict(scanned),
        descartadas_antes=dict(Counter(r['etapa'] for r in report if r['antes'])),
        descartadas_despues=dict(Counter(r['etapa'] for r in report if r['despues'])),
        recuperadas=dict(Counter(r['etapa'] for r in recovered)),
        obras_recuperadas={stage:dict(Counter(Path(r['archivo']).stem for r in recovered if r['etapa']==stage)) for stage in scanned},
        pruebas='Regresiones, créditos editoriales, sincronía de scripts e integridad de entradas: OK',
        huellas_entradas=before)
    (OUT/'resumen.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='huellas_entradas'}, ensure_ascii=False, indent=2))
    for r in recovered:
        if r['etapa']=='entrada_real_del_filtro':
            print(Path(r['archivo']).stem, r['linea'], r['texto'])


if __name__ == '__main__':
    main()
