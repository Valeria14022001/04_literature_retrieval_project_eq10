#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Valida la etapa de normalización de un corpus literario TSV.

Uso:
    python 06_validar_normalizacion.py
    python 06_validar_normalizacion.py --entrada datos/literature_raw_corpus.tsv \
        --normalizado datos/literature_normalized_corpus.tsv --modelo es_core_news_sm

Genera un CSV por fragmento y un TXT de resumen. No modifica los corpus.
La comprobación POS/lematización es de *consistencia con spaCy*, no una
certificación de corrección lingüística. Para ejecutarla se requiere el mismo
modelo y versión usados durante la normalización.
"""

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
import sys
import unicodedata

RAW_DEFAULT = Path("datos/literature_raw_corpus.tsv")
NORM_DEFAULT = Path("datos/literature_normalized_corpus.tsv")
CSV_DEFAULT = Path("datos/reporte_validacion_normalizacion.csv")
TXT_DEFAULT = Path("datos/resumen_validacion_normalizacion.txt")
REQUIRED_RAW = {"fragment_id", "title", "text"}
REQUIRED_NORM = REQUIRED_RAW | {"title_normalized", "text_normalized"}
POS_EXCLUIR = frozenset({"DET", "ADP", "CCONJ", "SCONJ", "PRON"})


def normalizar_espacios(texto):
    texto = unicodedata.normalize("NFC", texto or "")
    texto = "".join(" " if unicodedata.category(c) in {"Cc", "Cf", "Zl", "Zp"} else c for c in texto)
    return re.sub(r"\s+", " ", texto).strip()


def normalizar_doc(doc):
    terminos = []
    for token in doc:
        if token.is_space or token.is_punct or token.pos_ in POS_EXCLUIR or token.pos_ == "SYM":
            continue
        lema = normalizar_espacios(token.lemma_).lower()
        if lema and any(c.isalnum() for c in lema):
            terminos.append(lema)
    return " ".join(terminos)


def leer_tsv(ruta, requeridos):
    if not ruta.is_file():
        raise FileNotFoundError(f"No existe el archivo: {ruta}")
    with ruta.open("r", encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f, delimiter="\t")
        if not lector.fieldnames:
            raise ValueError(f"TSV sin encabezado: {ruta}")
        faltantes = requeridos - set(lector.fieldnames)
        if faltantes:
            raise ValueError(f"Faltan columnas en {ruta}: {', '.join(sorted(faltantes))}")
        filas = list(lector)
    if not filas:
        raise ValueError(f"TSV vacío: {ruta}")
    if any(None in f for f in filas):
        raise ValueError(f"Hay filas con más columnas que el encabezado: {ruta}")
    return filas


def indexar(filas, ruta):
    ids = [f["fragment_id"] for f in filas]
    if any(not x for x in ids):
        raise ValueError(f"Hay fragment_id vacíos en {ruta}")
    rep = [k for k, n in Counter(ids).items() if n > 1]
    if rep:
        raise ValueError(f"Hay fragment_id duplicados en {ruta}: {', '.join(rep[:10])}")
    return {f["fragment_id"]: f for f in filas}


def anomalias_formales(texto, campo, original):
    problemas = []
    if not texto:
        if normalizar_espacios(original):
            problemas.append(f"{campo}:resultado_vacio")
        return problemas
    if texto != texto.strip() or re.search(r"\s{2,}", texto):
        problemas.append(f"{campo}:espacios_irregulares")
    if texto != texto.lower():
        problemas.append(f"{campo}:mayusculas")
    if unicodedata.normalize("NFC", texto) != texto:
        problemas.append(f"{campo}:unicode_no_nfc")
    if any(unicodedata.category(c) in {"Cc", "Cf", "Zl", "Zp"} for c in texto):
        problemas.append(f"{campo}:caracteres_control")
    # La rutina original puede conservar puntuación interior de ciertos lemas;
    # por ello se marca como aviso, no como error determinante.
    if any(unicodedata.category(c).startswith("P") for c in texto):
        problemas.append(f"{campo}:posible_puntuacion_residual")
    return problemas


def main():
    p = argparse.ArgumentParser(description="Audita integridad y consistencia del corpus normalizado.")
    p.add_argument("--entrada", type=Path, default=RAW_DEFAULT)
    p.add_argument("--normalizado", type=Path, default=NORM_DEFAULT)
    p.add_argument("--reporte-csv", type=Path, default=CSV_DEFAULT)
    p.add_argument("--reporte-txt", type=Path, default=TXT_DEFAULT)
    p.add_argument("--modelo", default="es_core_news_sm")
    p.add_argument("--lote", type=int, default=32)
    p.add_argument("--sin-spacy", action="store_true", help="Solo integridad y controles formales; omite comparación contra spaCy.")
    args = p.parse_args()
    if args.lote < 1:
        p.error("--lote debe ser >= 1")
    if args.reporte_csv.resolve() == args.reporte_txt.resolve():
        p.error("Los dos reportes deben tener rutas distintas")
    corpus_paths = {args.entrada.resolve(), args.normalizado.resolve()}
    if any(r.resolve() in corpus_paths for r in (args.reporte_csv, args.reporte_txt)):
        p.error("La ruta de un reporte no puede sobrescribir un corpus")

    raw_rows = leer_tsv(args.entrada, REQUIRED_RAW)
    norm_rows = leer_tsv(args.normalizado, REQUIRED_NORM)
    raw = indexar(raw_rows, args.entrada)
    norm = indexar(norm_rows, args.normalizado)
    only_raw = sorted(raw.keys() - norm.keys())
    only_norm = sorted(norm.keys() - raw.keys())
    comunes = sorted(raw.keys() & norm.keys())
    reportes = []
    for fid in comunes:
        a, b = raw[fid], norm[fid]
        errores = []
        avisos = []
        for campo in ("title", "text"):
            if a[campo] != b[campo]:
                errores.append(f"{campo}:original_modificado")
            for problema in anomalias_formales(b[f"{campo}_normalized"], campo, a[campo]):
                (avisos if "posible_puntuacion" in problema else errores).append(problema)
        reportes.append({"fragment_id": fid, "errores": errores, "avisos": avisos,
                         "text_original_palabras": len(a["text"].split()),
                         "text_normalized_terminos": len(b["text_normalized"].split()),
                         "title_original_palabras": len(a["title"].split()),
                         "title_normalized_terminos": len(b["title_normalized"].split()),
                         "text_igual_al_original": b["text_normalized"] == a["text"],
                         "title_igual_al_original": b["title_normalized"] == a["title"]})

    modelo_version = "no ejecutado"
    if not args.sin_spacy and comunes:
        try:
            import spacy
            nlp = spacy.load(args.modelo, disable=["ner", "parser"])
        except (ImportError, OSError) as e:
            raise RuntimeError(f"No se pudo cargar spaCy/modelo {args.modelo}: {e}. Usa --sin-spacy para validación básica.") from e
        if "lemmatizer" not in nlp.pipe_names or not ({"tagger", "morphologizer"} & set(nlp.pipe_names)):
            raise RuntimeError("El modelo carece de lemmatizer o tagger/morphologizer")
        modelo_version = f"spaCy {spacy.__version__}; {args.modelo}; meta.version={nlp.meta.get('version','?')}"
        for campo in ("title", "text"):
            entradas = [normalizar_espacios(raw[fid][campo]) for fid in comunes]
            docs = nlp.pipe(entradas, batch_size=args.lote)
            for registro, doc, fid in zip(reportes, docs, comunes):
                esperado = normalizar_doc(doc)
                observado = norm[fid][f"{campo}_normalized"]
                if observado != esperado:
                    registro["errores"].append(f"{campo}:difiere_pipeline_spacy")

    for reg in reportes:
        reg["estado"] = "ERROR" if reg["errores"] else ("REVISAR" if reg["avisos"] else "OK")
    conteos = Counter(r["estado"] for r in reportes)
    tipos_error = Counter(x for r in reportes for x in r["errores"])
    tipos_aviso = Counter(x for r in reportes for x in r["avisos"])
    args.reporte_csv.parent.mkdir(parents=True, exist_ok=True)
    args.reporte_txt.parent.mkdir(parents=True, exist_ok=True)
    with args.reporte_csv.open("w", encoding="utf-8-sig", newline="") as f:
        campos = ["fragment_id", "estado", "errores", "avisos", "text_original_palabras",
                  "text_normalized_terminos", "title_original_palabras", "title_normalized_terminos",
                  "text_igual_al_original", "title_igual_al_original"]
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        for reg in reportes:
            w.writerow({**reg, "errores": "; ".join(reg["errores"]), "avisos": "; ".join(reg["avisos"])})
    resumen = [
        "VALIDACIÓN DEL CORPUS LITERARIO NORMALIZADO",
        f"Original: {args.entrada}", f"Normalizado: {args.normalizado}",
        f"Modelo verificación: {modelo_version}",
        f"Filas originales: {len(raw_rows)}; filas normalizadas: {len(norm_rows)}",
        f"IDs faltantes en normalizado: {len(only_raw)}; IDs inesperados: {len(only_norm)}",
        f"IDs faltantes (hasta 30): {', '.join(only_raw[:30]) or 'ninguno'}",
        f"IDs inesperados (hasta 30): {', '.join(only_norm[:30]) or 'ninguno'}",
        f"Coincidencias: {len(comunes)}; OK: {conteos['OK']}; REVISAR: {conteos['REVISAR']}; ERROR: {conteos['ERROR']}",
        f"Texto normalizado igual al original: {sum(r['text_igual_al_original'] for r in reportes)}",
        f"Título normalizado igual al original: {sum(r['title_igual_al_original'] for r in reportes)}",
        "Errores por tipo: " + (json.dumps(dict(tipos_error), ensure_ascii=False, sort_keys=True) if tipos_error else "ninguno"),
        "Avisos por tipo: " + (json.dumps(dict(tipos_aviso), ensure_ascii=False, sort_keys=True) if tipos_aviso else "ninguno"),
        "INTERPRETACIÓN: la coincidencia con spaCy verifica reproducibilidad, no exactitud lingüística.",
        "Revise manualmente muestras de diferentes autores, obras y casos señalados.",
    ]
    args.reporte_txt.write_text("\n".join(resumen) + "\n", encoding="utf-8")
    print("\n".join(resumen))
    print(f"\nReporte por fragmento: {args.reporte_csv}\nResumen: {args.reporte_txt}")
    return 1 if only_raw or only_norm or conteos["ERROR"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, ValueError, FileNotFoundError, OSError, csv.Error) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(2)
