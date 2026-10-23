import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import joblib
from scipy import sparse
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer

ENTRADA = Path('datos/literature_normalized_corpus.tsv')
SALIDA = Path('vectorizacion')
CAMPOS = {'titulo': 'title_normalized', 'texto': 'text_normalized'}
REPRESENTACIONES = ('frecuencia', 'binaria', 'tfidf')


def vectorizador(tipo, ngrama=1):
    if tipo not in REPRESENTACIONES or ngrama not in (1, 2):
        raise ValueError('Representación o tamaño de ngrama no admitido.')
    # La normalización ya produjo tokens: no volver a dividir nombres,
    # eliminar iniciales, quitar acentos ni aplicar otra lista de stopwords.
    opciones = dict(tokenizer=str.split, token_pattern=None, lowercase=False,
                    ngram_range=(ngrama, ngrama))
    if tipo == 'tfidf':
        return TfidfVectorizer(**opciones, norm='l2', smooth_idf=True)
    return CountVectorizer(**opciones, binary=tipo == 'binaria')


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
    if any(None in fila or any(v is None for v in fila.values()) for fila in filas):
        raise ValueError('TSV con filas incompletas o columnas sobrantes.')
    if not filas:
        raise ValueError('El corpus normalizado no contiene registros.')
    ids = [(fila['fragment_id'] or '').strip() for fila in filas]
    if any(not x for x in ids) or len(set(ids)) != len(ids):
        raise ValueError('Los fragment_id deben ser únicos y no vacíos.')
    return filas, ids


def rutas(salida, campo, tipo, ngrama=2):
    nombre = f'{campo}_{"unigramas" if ngrama == 1 else "bigramas"}_{tipo}'
    return salida / 'matrices' / f'{nombre}.npz', salida / 'vectorizadores' / f'{nombre}.joblib'


def generar(entrada, salida):
    filas, ids = cargar_corpus(entrada)
    salida.mkdir(parents=True, exist_ok=True)
    metadata_path = entrada.with_name('normalizacion.json')
    normalizacion = json.loads(metadata_path.read_text(encoding='utf-8'))
    if normalizacion['sha256_normalizado'] != hashlib.sha256(entrada.read_bytes()).hexdigest():
        raise ValueError('Regenera la normalización: sus metadatos no corresponden al TSV.')
    resultados = {}
    for campo, columna in CAMPOS.items():
        textos = [(f[columna] or '').strip() for f in filas]
        for ngrama, tipo in ((n,t) for n in (1,2) for t in REPRESENTACIONES):
            vec = vectorizador(tipo, ngrama)
            try:
                X = vec.fit_transform(textos)
            except ValueError as exc:
                raise ValueError(
                    f'No se pudieron extraer ngramas de tamaño {ngrama} de {columna}: {exc}'
                ) from exc
            ruta_matriz, ruta_vec = rutas(salida, campo, tipo, ngrama)
            ruta_matriz.parent.mkdir(parents=True,exist_ok=True)
            ruta_vec.parent.mkdir(parents=True,exist_ok=True)
            sparse.save_npz(ruta_matriz, X)
            joblib.dump(vec, ruta_vec)
            resultados[f'{campo}_{ngrama}_{tipo}'] = {
                'campo': campo, 'ngrama': ngrama, 'tipo': tipo,
                'matriz': ruta_matriz.relative_to(salida).as_posix(),
                'vectorizador': ruta_vec.relative_to(salida).as_posix(),
                'documentos': int(X.shape[0]),
                'caracteristicas': int(X.shape[1]),
                'valores_no_cero': int(X.nnz),
                'filas_sin_terminos': [ids[i] for i,n in enumerate(X.getnnz(axis=1)) if n == 0],
            }
            print(f'{campo:6} | n={ngrama} | {tipo:10} | {X.shape[0]} documentos x {X.shape[1]} características')

    with (salida / 'ids_documentos.tsv').open('w', encoding='utf-8', newline='') as f:
        escritor = csv.writer(f, delimiter='\t')
        escritor.writerow(['row_index', 'fragment_id'])
        escritor.writerows(enumerate(ids))

    manifiesto = {
        'fase': 6,
        'normalizacion': normalizacion,
        'contenido': 'unigramas y bigramas en espacios separados',
        'ngram_ranges': [[1, 1], [2, 2]],
        'corpus_entrada': str(entrada),
        'sha256_corpus': hashlib.sha256(entrada.read_bytes()).hexdigest(),
        'cantidad_documentos': len(ids),
        'campos': CAMPOS,
        'representaciones': resultados,
        'tokenizacion': 'str.split sobre los campos ya normalizados; sin segundo filtrado',
        'nota': 'La fila i de cada matriz corresponde a la fila i de ids_documentos.tsv.',
        'consultas': 'Normalizar primero con la misma función y modelo spaCy de la fase 5; después usar transform(), nunca fit_transform().',
    }
    import sklearn, scipy
    manifiesto['versiones'] = dict(sklearn=sklearn.__version__, scipy=scipy.__version__, joblib=joblib.__version__)
    (salida / 'manifiesto.json').write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\nListo: 12 matrices, 12 vectorizadores, IDs y manifiesto en {salida}')


def transformar_consulta_normalizada(consulta, salida, campo='texto', representacion='tfidf', ngrama=1):
    if campo not in CAMPOS:
        raise ValueError('Campo no admitido.')
    vectorizador(representacion, ngrama)  # validar opciones antes de construir la ruta
    _, ruta_vec = rutas(Path(salida), campo, representacion, ngrama)
    # Cargar únicamente artefactos propios/de confianza: joblib utiliza pickle.
    return joblib.load(ruta_vec).transform([consulta])


def main():
    p = argparse.ArgumentParser(description='Genera VSM para título/texto, unigramas/bigramas y tres representaciones.')
    p.add_argument('--entrada', type=Path, default=ENTRADA)
    p.add_argument('--salida', type=Path, default=SALIDA)
    args = p.parse_args()
    try:
        generar(args.entrada, args.salida)
    except (ValueError, OSError, csv.Error) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
