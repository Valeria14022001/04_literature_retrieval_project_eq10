import argparse
import csv
import hashlib
import json
from pathlib import Path

import joblib
from scipy import sparse
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer

ENTRADA = Path('datos/literature_normalized_corpus.tsv')
SALIDA = Path('datos/vectorizacion')
CAMPOS = {'titulo': 'title_normalized', 'texto': 'text_normalized'}
REPRESENTACIONES = ('frecuencia', 'binaria', 'tfidf')


def vectorizador(tipo):
    pass


def cargar_corpus(ruta):
    if not ruta.is_file():
        raise FileNotFoundError(f'No existe el corpus normalizado: {ruta}')
    with ruta.open(encoding='utf-8-sig', newline='') as f:
        lector = csv.DictReader(f, delimiter='\t')
        requeridas = {'fragment_id', *CAMPOS.values()}
        faltantes = requeridas - set(lector.fieldnames or [])
        if faltantes:
            raise ValueError(f'Faltan campos requeridos: {sorted(faltantes)}')
        filas = list(lector)
    if not filas:
        raise ValueError('El corpus normalizado no contiene registros.')
    ids = [(fila['fragment_id'] or '').strip() for fila in filas]
    if any(not x for x in ids) or len(set(ids)) != len(ids):
        raise ValueError('Los fragment_id deben ser únicos y no vacíos.')
    return filas, ids


def rutas(salida, campo, tipo):
    nombre = f'{campo}_bigramas_{tipo}'
    return salida / f'{nombre}.npz', salida / f'{nombre}.joblib'


def generar(entrada, salida):
    filas, ids = cargar_corpus(entrada)
    salida.mkdir(parents=True, exist_ok=True)
    resultados = {}
    for campo, columna in CAMPOS.items():
        textos = [(f[columna] or '').strip() for f in filas]
        for tipo in REPRESENTACIONES:
            vec = vectorizador(tipo)
            try:
                X = vec.fit_transform(textos)
            except ValueError as exc:
                raise ValueError(
                    f'No se pudieron extraer bigramas de {columna}. '
                    'Comprueba que haya al menos un documento con dos tokens consecutivos.'
                ) from exc
            ruta_matriz, ruta_vec = rutas(salida, campo, tipo)
            sparse.save_npz(ruta_matriz, X)
            joblib.dump(vec, ruta_vec)
            resultados[f'{campo}_{tipo}'] = {
                'matriz': ruta_matriz.name,
                'vectorizador': ruta_vec.name,
                'documentos': int(X.shape[0]),
                'caracteristicas': int(X.shape[1]),
                'valores_no_cero': int(X.nnz),
            }
            print(f'{campo:6} | {tipo:10} | {X.shape[0]} documentos x {X.shape[1]} bigramas')

    with (salida / 'ids_documentos.tsv').open('w', encoding='utf-8', newline='') as f:
        escritor = csv.writer(f, delimiter='\t')
        escritor.writerow(['row_index', 'fragment_id'])
        escritor.writerows(enumerate(ids))

    manifiesto = {
        'fase': 6,
        'contenido': 'bigramas exclusivamente',
        'ngram_range': [2, 2],
        'corpus_entrada': str(entrada),
        'sha256_corpus': hashlib.sha256(entrada.read_bytes()).hexdigest(),
        'cantidad_documentos': len(ids),
        'campos': CAMPOS,
        'representaciones': resultados,
        'nota': 'La fila i de cada matriz corresponde a la fila i de ids_documentos.tsv.',
        'consultas': 'Normalizar primero con la misma función y modelo spaCy de la fase 5; después usar transform(), nunca fit_transform().',
    }
    (salida / 'manifiesto.json').write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\nListo: 6 matrices, 6 vectorizadores, IDs y manifiesto en {salida}')


def transformar_consulta_normalizada(consulta, salida, campo='texto', representacion='tfidf'):
    pass


def main():
    pass


if __name__ == '__main__':
    main()
