"""Búsqueda VSM: normalización compartida, coseno y Top-10 trazable."""
import argparse
import csv
import hashlib
import html
import importlib.util
import json
from pathlib import Path
import sys

import joblib
import numpy as np
from scipy import sparse
from sklearn.metrics.pairwise import cosine_similarity
import spacy

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT/'datos'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read_tsv(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f, delimiter='\t'))

class Buscador:
    def __init__(self, directorio=ROOT/'vectorizacion', modelo='es_core_news_sm'):
        self.directory = Path(directorio).resolve()
        self.manifest = json.loads((self.directory/'manifiesto.json').read_text(encoding='utf-8'))
        source = Path(self.manifest['corpus_entrada'])
        self.source = source if source.is_absolute() else ROOT/source
        if sha(self.source) != self.manifest['sha256_corpus']:
            raise ValueError('El corpus cambió: regenerar sus representaciones antes de consultar.')
        self.rows = read_tsv(self.source)
        ids = read_tsv(self.directory/'ids_documentos.tsv')
        if [r['fragment_id'] for r in self.rows] != [r['fragment_id'] for r in ids] or [int(r['row_index']) for r in ids] != list(range(len(ids))):
            raise ValueError('La correspondencia entre matrices, IDs y corpus es inconsistente.')
        if len({r['fragment_id'] for r in self.rows}) != len(self.rows):
            raise ValueError('IDs duplicados en el corpus.')
        self.normalizer_path = ROOT/'scripts/05_normalizar_corpus.py'
        spec = importlib.util.spec_from_file_location('normalizador_consultas', self.normalizer_path)
        self.normalizer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.normalizer)
        self.nlp = spacy.load(modelo, disable=['ner','parser'])
        provenance = self.manifest['normalizacion']
        if (modelo != provenance['modelo'] or self.nlp.meta['version'] != provenance['modelo_version'] or
            spacy.__version__ != provenance['spacy'] or
            sha(self.normalizer_path) != provenance['politica_sha256']):
            raise ValueError('Modelo o normalizador diferente del corpus. Regenera normalización y vectorización.')
        # Solo compatibilidad operativa; no se vuelve a normalizar todo el corpus.
        self.cache = {}

    def buscar(self, consulta, contenido, ngrama, representacion, query_id='Q01'):
        if not consulta.strip() or not query_id.strip():
            raise ValueError('La consulta y query_id no pueden estar vacíos.')
        if contenido not in ('titulo','texto') or ngrama not in (1,2) or representacion not in ('frecuencia','binaria','tfidf'):
            raise ValueError('Configuración de búsqueda no admitida.')
        key = f'{contenido}_{ngrama}_{representacion}'
        if key not in self.cache:
            info = self.manifest['representaciones'][key]
            matrix = sparse.load_npz(self.directory/info['matriz'])
            vec = joblib.load(self.directory/info['vectorizador'])
            if matrix.shape != (len(self.rows),len(vec.vocabulary_)) or not np.isfinite(matrix.data).all():
                raise ValueError('Matriz o vocabulario incompatible con el corpus.')
            self.cache[key] = matrix, vec
        matrix, vec = self.cache[key]
        normalized = self.normalizer.normalizar_doc(self.nlp(self.normalizer.preparar_para_spacy(consulta)))
        query = vec.transform([normalized])
        features = vec.build_analyzer()(normalized)
        outside = sorted(set(features)-set(vec.vocabulary_))
        scores = cosine_similarity(query, matrix).ravel()
        if not np.isfinite(scores).all():
            raise ValueError('Se obtuvieron puntuaciones no finitas.')
        # Empates: orden estable por ID, sin atribuir relevancia a un cero.
        order = sorted(range(len(scores)), key=lambda i:(-float(scores[i]),self.rows[i]['fragment_id']))[:10]
        results = [dict(query_id=query_id, document_id=self.rows[i]['fragment_id'], rank=rank,
                        score=float(scores[i]), title=self.rows[i]['title'], author=self.rows[i]['author'],
                        book_id=self.rows[i]['book_id'], chapter_position=self.rows[i]['chapter_position'],
                        text=self.rows[i]['text'], source=self.rows[i]['source'], url=self.rows[i]['url'])
                   for rank,i in enumerate(order,1)]
        warnings = []
        if not normalized:
            warnings.append('La consulta quedó vacía tras la normalización.')
        elif query.nnz == 0:
            warnings.append('La consulta no tiene características presentes en este vocabulario.')
        if np.count_nonzero(scores > 0) < 10:
            warnings.append('Hay menos de diez documentos con similitud positiva. Los ceros completan el Top-10 y no indican coincidencia.')
        if outside:
            warnings.append('Algunas características de la consulta no están en el vocabulario.')
        return dict(query_id=query_id, consulta=consulta, consulta_normalizada=normalized,
                    contenido=contenido, ngrama=ngrama, representacion=representacion,
                    documentos_similitud_positiva=int(np.count_nonzero(scores > 0)),
                    caracteristicas_fuera_vocabulario=outside, avisos=warnings, resultados=results,
                    sha256_corpus=sha(self.source), sha256_normalizador=sha(self.normalizer_path),
                    modelo=self.nlp.meta['name'], modelo_version=self.nlp.meta['version'], spacy=spacy.__version__)

def guardar(result, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory/'consulta.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    with (directory/'rankings.tsv').open('w',encoding='utf-8',newline='') as f:
        w = csv.DictWriter(f,fieldnames=['query_id','document_id','rank','score'],delimiter='\t')
        w.writeheader()
        w.writerows({k:r[k] for k in w.fieldnames} for r in result['resultados'])
    esc = lambda value: html.escape(str(value))
    cards = ''.join(f'<article><h2>{r["rank"]}. {esc(r["title"])} — {esc(r["document_id"])}</h2><p>{esc(r["author"])} · Coseno: {r["score"]:.8f}</p><p>{esc(r["chapter_position"])}</p><details><summary>Leer fragmento original completo</summary><pre>{esc(r["text"])}</pre></details></article>' for r in result['resultados'])
    page = f'''<!doctype html><html lang="es"><meta charset="utf-8"><title>Recuperación literaria: Top-10</title>
<style>body{{font:17px/1.6 system-ui;max-width:1000px;margin:40px auto;padding:20px;color:#172635}}article{{border-top:1px solid #ccd;padding:16px 0}}pre{{white-space:pre-wrap;font:17px/1.7 Georgia}}.aviso{{background:#fff0d2;padding:12px}}</style>
<h1>Recuperación literaria: Top-10</h1><p>Consulta: {esc(result['consulta'])}</p><p>Normalizada: {esc(result['consulta_normalizada'])}</p>
<p>Contenido: {esc(result['contenido'])} · Ngrama: {result['ngrama']} · Representación: {esc(result['representacion'])}</p>
<p>Desempate por ID. Similitud léxica; no equivale a juicio de relevancia.</p>
{''.join('<p class="aviso">'+esc(x)+'</p>' for x in result['avisos'])}{cards}</html>'''
    (directory/'informe.html').write_text(page,encoding='utf-8')

def main():
    parser = argparse.ArgumentParser(description='Consulta literaria libre y Top-10 por coseno; corpus en español.')
    parser.add_argument('--consulta', required=True)
    parser.add_argument('--contenido',choices=['titulo','texto'],required=True)
    parser.add_argument('--ngrama',type=int,choices=[1,2],required=True)
    parser.add_argument('--representacion',choices=['frecuencia','binaria','tfidf'],required=True)
    parser.add_argument('--query-id',default='Q01')
    parser.add_argument('--vectorizacion',type=Path,default=ROOT/'vectorizacion')
    parser.add_argument('--salida',type=Path,default=ROOT/'resultados/consultas/ultima_consulta')
    args = parser.parse_args()
    try:
        engine = Buscador(args.vectorizacion)
        result = engine.buscar(args.consulta,args.contenido,args.ngrama,args.representacion,args.query_id)
        guardar(result,args.salida)
        print('Consulta normalizada:',result['consulta_normalizada'])
        print(f'Contenido: {args.contenido} | Ngrama: {args.ngrama} | Representación: {args.representacion}')
        for warning in result['avisos']:
            print('AVISO:',warning)
        for r in result['resultados']:
            print(f'{r["rank"]:2}. {r["score"]:.8f} | {r["document_id"]} | {r["title"]} | {r["author"]}')
            print('    '+' '.join(r['text'].split())[:220])
        print('Archivos:',args.salida)
    except (ValueError,OSError,KeyError,ImportError,csv.Error) as exc:
        print(f'ERROR: {exc}',file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
