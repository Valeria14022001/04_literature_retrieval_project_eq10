import argparse
import hashlib
import json
import csv
import os
from pathlib import Path
import re
import sys
import tempfile
import unicodedata

ENTRADA_PREDETERMINADA = Path("datos/literature_raw_corpus.tsv")
SALIDA_PREDETERMINADA = Path("datos/literature_normalized_corpus.tsv")
DEMO_ENTRADA = Path("datos/demo/literature_raw_corpus.tsv")

POS_EXCLUIR = frozenset({"DET", "ADP", "CCONJ", "SCONJ", "PRON"})

CAMPOS_OBLIGATORIOS = (
    "fragment_id", "book_id", "title", "author", "chapter_position",
    "text", "language", "source", "url",
)

EJEMPLOS = [
    {
        "fragment_id": "F0001", "book_id": "obra_demo_01",
        "title": "El bosque y la tormenta", "author": "Autora ficticia",
        "chapter_position": "Capítulo I (parte 1/2)",
        "text": "La niña caminaba por el bosque. De pronto, una tormenta oscura llegó. "
                "Ella buscó refugio entre los árboles y no encontró su casa.",
        "language": "es", "source": "Sintético", "url": "",
        "tipo": "cuento", "genero": "aventura", "epoca": "ficticia",
    },
    {
        "fragment_id": "F0002", "book_id": "obra_demo_02",
        "title": "Una promesa entre hermanos", "author": "Autor ficticio",
        "chapter_position": "Capítulo II",
        "text": "Los hermanos discutieron porque uno rompió la promesa. "
                "Después se abrazaron y decidieron viajar juntos.",
        "language": "es", "source": "Sintético", "url": "",
        "tipo": "novela_corta", "genero": "realismo", "epoca": "ficticia",
    },
    {
        "fragment_id": "F0003", "book_id": "obra_demo_03",
        "title": "La decisión de Isabel", "author": "Escritora ficticia",
        "chapter_position": "Sección 3",
        "text": "Isabel descubrió un secreto, pero no reveló la verdad. "
                "Al amanecer, escribió una carta para su amiga.",
        "language": "es", "source": "Sintético", "url": "",
        "tipo": "novela", "genero": "misterio", "epoca": "ficticia",
    },
]


def normalizar_espacios(texto: str) -> str:
    """Convierte controles y espacios (incluidos saltos) a un solo espacio."""
    texto = unicodedata.normalize("NFC", texto or "")
    texto = "".join(" " if unicodedata.category(c) in {"Cc", "Cf", "Zl", "Zp"} else c for c in texto)
    return re.sub(r"\s+", " ", texto).strip()


def normalizar_doc(doc) -> str:
    """Normaliza un Doc de spaCy. Reutilizar también para consultas futuras.

    Se excluyen únicamente POS pedidos y tokens no léxicos (puntuación,
    espacios y símbolos). No se eliminan stopwords de otras categorías.
    """
    terminos = []
    for token in doc:
        if token.is_space or token.is_punct or token.pos_ in POS_EXCLUIR:
            continue
        # Los símbolos aislados no representan unidades léxicas útiles.
        if token.pos_ == "SYM":
            continue
        lema = normalizar_espacios(token.lemma_).lower()
        if not lema or not any(caracter.isalnum() for caracter in lema):
            continue
        terminos.append(lema)
    return " ".join(terminos)


def preparar_para_spacy(texto: str) -> str:
    """Separa rayas y guiones de diálogo solo en la vista de análisis."""
    texto = normalizar_espacios(texto)
    return normalizar_espacios(re.sub(
        r"[—–]|(?<!\w)-(?=[^\W\d_]|[¡¿«“])|(?<=[^\W\d_])-(?=\s|[¡¿.!?,;:»”]|$)",
        " ", texto))


def crear_demo(ruta: Path, forzar: bool = False) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if ruta.exists() and not forzar:
        raise FileExistsError(f"La muestra ya existe: {ruta}. Usa --sobrescribir-demo para reemplazarla.")
    columnas = list(EJEMPLOS[0].keys())
    with ruta.open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas, delimiter="\t", lineterminator="\n")
        escritor.writeheader()
        escritor.writerows(EJEMPLOS)
    print(f"Ejemplo: {ruta} ({len(EJEMPLOS)})")
    pass


def procesar(entrada: Path, salida: Path, modelo: str, lote: int = 32) -> None:
    try:
        import spacy
    except ImportError as exc:
        raise RuntimeError('spaCy no está instalado. Ejecuta: pip install "spacy>=3.7,<4"') from exc

    try:
        nlp = spacy.load(modelo, disable=["ner", "parser"])
    except OSError as exc:
        raise RuntimeError(
            f"No está instalado el modelo '{modelo}'. Ejecuta: python -m spacy download {modelo}"
        ) from exc
    if "tagger" not in nlp.pipe_names and "morphologizer" not in nlp.pipe_names:
        raise RuntimeError("El modelo debe incluir etiquetado POS (tagger o morphologizer); spacy.blank('es') no sirve.")
    if "lemmatizer" not in nlp.pipe_names:
        raise RuntimeError("El modelo debe incluir lematizador; no se aceptan lemas vacíos ni tokenización simple.")

    if not entrada.is_file():
        raise FileNotFoundError(f"No existe el corpus de entrada: {entrada}")
    if entrada.resolve() == salida.resolve():
        raise ValueError("La entrada y la salida no deben apuntar al mismo archivo.")

    with entrada.open("r", encoding="utf-8-sig", newline="") as archivo:
        lector = csv.DictReader(archivo, delimiter="\t")
        if not lector.fieldnames:
            raise ValueError("El TSV no contiene encabezados.")
        columnas = list(lector.fieldnames)
        faltantes = sorted(set(CAMPOS_OBLIGATORIOS) - set(columnas))
        if faltantes:
            raise ValueError(f"Faltan columnas requeridas de la fase 4: {', '.join(faltantes)}")
        if "title_normalized" in columnas or "text_normalized" in columnas:
            raise ValueError("Parece un corpus ya normalizado. Usa como entrada el corpus crudo.")
        filas = list(lector)

    ids = [f["fragment_id"] for f in filas]
    if not filas:
        raise ValueError("El corpus está vacío.")
    if not all(ids) or len(set(ids)) != len(ids):
        raise ValueError("fragment_id debe ser no vacío y único para cada fila.")

    # Normalizar ambos campos a través del MISMO pipeline spaCy.
    titulos = [preparar_para_spacy(f["title"]) for f in filas]
    textos = [preparar_para_spacy(f["text"]) for f in filas]
    titulos_norm = [normalizar_doc(d) for d in nlp.pipe(titulos, batch_size=lote)]
    textos_norm = [normalizar_doc(d) for d in nlp.pipe(textos, batch_size=lote)]

    salida.parent.mkdir(parents=True, exist_ok=True)
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", suffix=".tsv",
                                         prefix=".normalizado_", dir=salida.parent, delete=False) as archivo:
            temporal = Path(archivo.name)
            columnas_salida = columnas + ["title_normalized", "text_normalized"]
            escritor = csv.DictWriter(archivo, fieldnames=columnas_salida, delimiter="\t", lineterminator="\n")
            escritor.writeheader()
            for fila, titulo, texto in zip(filas, titulos_norm, textos_norm):
                fila["title_normalized"] = titulo
                fila["text_normalized"] = texto
                escritor.writerow(fila)
        os.replace(temporal, salida)
    finally:
        if temporal is not None and temporal.exists():
            temporal.unlink()

    # Metadatos producidos aquí, sin ejecutar un validador independiente.
    metadatos = dict(modelo=modelo, modelo_version=nlp.meta['version'], spacy=spacy.__version__,
        idioma=nlp.lang, politica_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        sha256_original=hashlib.sha256(entrada.read_bytes()).hexdigest(),
        sha256_normalizado=hashlib.sha256(salida.read_bytes()).hexdigest(), fragmentos=len(filas))
    salida.with_name('normalizacion.json').write_text(json.dumps(metadatos,ensure_ascii=False,indent=2),encoding='utf-8')

    print(f"Corpus normalizado: {salida}")
    print(f"Filas: {len(filas)} | Modelo: {modelo} | POS excluidos: {', '.join(sorted(POS_EXCLUIR))}")
    print(f"Campos añadidos: title_normalized, text_normalized (originales preservados)")
    print(f"Normalizaciones que fallaron: {sum(not x for x in textos_norm)}")
    print("Ejemplo: ")
    print(f"  ID: {ids[0]}")
    print(f"  Título normalizado: {titulos_norm[0]}")
    print(f"  Texto normalizado: {textos_norm[0][:220]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fase 5: POS tagging + lematización de título y fragmento.")
    parser.add_argument("--entrada", type=Path, default=ENTRADA_PREDETERMINADA)
    parser.add_argument("--salida", type=Path, default=SALIDA_PREDETERMINADA)
    parser.add_argument("--modelo", default="es_core_news_sm", help="Modelo spaCy español con POS y lemas.")
    parser.add_argument("--lote", type=int, default=32)
    parser.add_argument("--crear-demo", action="store_true", help="Crea muestra sintética y termina.")
    parser.add_argument("--ruta-demo", type=Path, default=DEMO_ENTRADA)
    parser.add_argument("--sobrescribir-demo", action="store_true")
    args = parser.parse_args()

    try:
        if args.crear_demo:
            crear_demo(args.ruta_demo, forzar=args.sobrescribir_demo)
        else:
            if args.lote < 1:
                raise ValueError("--lote debe ser mayor o igual que 1.")
            procesar(args.entrada, args.salida, args.modelo, args.lote)
    except (RuntimeError, ValueError, FileNotFoundError, FileExistsError, OSError, csv.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
