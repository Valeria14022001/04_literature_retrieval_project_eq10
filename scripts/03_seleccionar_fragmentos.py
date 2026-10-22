from collections import Counter, defaultdict
from pathlib import Path
import argparse
import csv
import hashlib
import json
import sys

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config_seleccion as cfg  # noqa: E402


RUTA_CANDIDATOS = Path("datos/candidatos/candidatos.tsv")
RUTA_OVERRIDES = Path("datos/overrides_seleccion.csv")
RUTA_CORPUS = Path("datos/literature_raw_corpus.tsv")
CARPETA_SELECCION = Path("datos/seleccion")

TIPOS_VALIDOS = ("novela", "novela_corta", "cuento")

CAMPOS_CORPUS = [
    "fragment_id", "book_id", "title", "author", "chapter_position", "text",
    "language", "source", "url",
    # extras para analisis y etapas siguientes
    "tipo", "genero", "epoca", "idioma_original", "pais_origen",
    "position_rel", "n_words", "narrative_role", "zone", "importance",
    "winning_query", "candidato_id",
]

CAMPOS_REPORTE_SELECCION = [
    "book_id", "title", "author", "tipo", "palabras_totales", "candidatos",
    "elegibles", "cuota", "seleccionados", "zonas_vacias", "nota",
]


# ----------------------------------------------------------------------------
# Lectura
# ----------------------------------------------------------------------------

def leer_candidatos(ruta):
    filas = []

    with open(ruta, "r", encoding="utf-8", newline="") as archivo:
        for fila in csv.DictReader(archivo, delimiter="\t"):
            fila["n_palabras"] = int(fila["n_palabras"])
            fila["parte"] = int(fila["parte"])
            fila["n_partes"] = int(fila["n_partes"])

            for campo in ("pos_inicio_rel", "pos_fin_rel", "centro_rel"):
                fila[campo] = float(fila[campo])

            filas.append(fila)

    return filas


def leer_overrides(ruta):
    incluir, excluir = set(), set()

    if not ruta.exists():
        return incluir, excluir

    with open(ruta, "r", encoding="utf-8", newline="") as archivo:
        for fila in csv.DictReader(archivo):
            clave = ((fila.get("book_id") or "").strip(), (fila.get("candidato_id") or "").strip())
            accion = (fila.get("accion") or "").strip().lower()

            if accion == "incluir":
                incluir.add(clave)
            elif accion == "excluir":
                excluir.add(clave)

    return incluir, excluir


def huella_archivo(ruta):
    return hashlib.sha1(ruta.read_bytes()).hexdigest()


# ----------------------------------------------------------------------------
# Importancia (por obra)
# ----------------------------------------------------------------------------

def puntuar_obra(cands):
    """
    Agrega a cada candidato (dict) de UNA obra:
      q_score      cercania a las consultas de "momento importante" (0-1)
      central      cercania al vocabulario central de la obra (0-1)
      consulta_ganadora
    El TF-IDF se ajusta con todos los candidatos de la obra.
    """
    n = len(cands)

    if n == 1:
        cands[0].update(q_score=1.0, central=1.0, consulta_ganadora="unico_fragmento")
        return

    try:
        vec = TfidfVectorizer(tokenizer=cfg.tokenizar, lowercase=False,
                              token_pattern=None, sublinear_tf=True)
        X = vec.fit_transform([c["text"] for c in cands])
    except ValueError:
        for c in cands:
            c.update(q_score=0.0, central=0.0, consulta_ganadora="ninguna")
        return

    nombres = list(cfg.CONSULTAS_IMPORTANTES)
    Q = vec.transform([cfg.CONSULTAS_IMPORTANTES[k] for k in nombres])

    sims = cosine_similarity(X, Q)
    sims = sims / (sims.max(axis=0) + 1e-9)          # cada consulta aporta su mejor fragmento
    q_score = sims.max(axis=1)
    ganadora = [nombres[j] if q_score[i] > 0 else "ninguna"
                for i, j in enumerate(sims.argmax(axis=1))]

    centroide = np.asarray(X.mean(axis=0))
    central = cosine_similarity(X, centroide).ravel()
    central = (central - central.min()) / (central.max() - central.min() + 1e-9)

    for i, c in enumerate(cands):
        c["q_score"] = float(q_score[i])
        c["central"] = float(central[i])
        c["consulta_ganadora"] = ganadora[i]


def puntaje_en_zona(cand, zona):
    """Importancia final del candidato dentro de su zona: consultas + centralidad + cercania al punto objetivo."""
    lo, hi, objetivo = zona
    semiancho = max(objetivo - lo, min(hi, 1.0) - objetivo, 1e-9)
    posicion = max(0.0, 1.0 - abs(cand["centro_rel"] - objetivo) / semiancho)

    w = cfg.PESOS
    puntaje = w["consultas"] * cand["q_score"] + w["centralidad"] * cand["central"] + w["posicion"] * posicion

    if cand["n_palabras"] < cfg.PREFERIDO_MIN_PALABRAS:
        puntaje -= cfg.PENALIZACION_CORTO

    return puntaje


# ----------------------------------------------------------------------------
# Tipo, cuotas y zonas
# ----------------------------------------------------------------------------

def tipo_de_obra(cands, total_palabras, umbral_novela):
    declarado = (cands[0].get("tipo") or "").strip().lower()

    if declarado in TIPOS_VALIDOS:
        return declarado, ""

    nota = "tipo inferido por longitud" if not declarado else \
           f"tipo '{declarado}' no reconocido; inferido por longitud"

    return ("novela" if total_palabras >= umbral_novela else "cuento"), nota


def cuota_de_obra(obra, escala, args):
    if obra["tipo"] == "cuento":
        k = args.fragmentos_cuento
    else:
        k = round(escala * obra["total"] / args.palabras_por_fragmento)
        k = max(args.min_novela, min(args.max_novela, k))

        # cobertura maxima: los fragmentos elegidos no deben ser mas de cierta
        # fraccion de la obra (protege a las novelas cortas)
        if obra["elegibles"]:
            media = sum(c["n_palabras"] for c in obra["elegibles"]) / len(obra["elegibles"])
            tope = int(args.max_cobertura * obra["total"] / max(media, 1))
            k = min(k, max(tope, cfg.FRAGMENTOS_CUENTO))

    return min(k, len(obra["elegibles"]))


def zonas_de_obra(tipo, k):
    """Lista de (desde, hasta, punto_objetivo) con posiciones relativas 0-1."""
    if tipo == "cuento" and k == len(cfg.ZONAS_CUENTO):
        return list(cfg.ZONAS_CUENTO)

    return [(i / k, (i + 1) / k if i < k - 1 else 1.01, (i + 0.5) / k) for i in range(k)]


def elegir_por_zonas(elegibles, zonas):
    """
    Un fragmento por zona: el de mayor puntaje dentro de la zona (sin mover
    fragmentos de una zona a otra). Si una zona queda sin candidatos, se toma el
    mas cercano a su punto objetivo. Devuelve (lista de (candidato, etiqueta_zona), zonas_vacias).
    """
    if len(elegibles) <= len(zonas):
        return [(c, "todas") for c in sorted(elegibles, key=lambda c: c["centro_rel"])], 0

    usados = set()
    por_capitulo = Counter()
    elegidos = []
    vacias = 0

    for numero, zona in enumerate(zonas, start=1):
        lo, hi, objetivo = zona
        miembros = [c for c in elegibles
                    if lo <= c["centro_rel"] < hi and c["candidato_id"] not in usados]

        if not miembros:
            vacias += 1
            restantes = [c for c in elegibles if c["candidato_id"] not in usados]
            miembros = [min(restantes, key=lambda c: (abs(c["centro_rel"] - objetivo), c["candidato_id"]))]

        for c in miembros:
            c["importancia"] = round(puntaje_en_zona(c, zona), 4)

        orden = sorted(miembros, key=lambda c: (-c["importancia"], c["centro_rel"], c["candidato_id"]))
        elegido = next((c for c in orden if por_capitulo[c["capitulo"]] < cfg.MAX_POR_CAPITULO), orden[0])

        usados.add(elegido["candidato_id"])
        por_capitulo[elegido["capitulo"]] += 1
        elegidos.append((elegido, f"{numero}/{len(zonas)}"))

    return sorted(elegidos, key=lambda x: x[0]["centro_rel"]), vacias


def rol_narrativo(cand):
    if cand["pos_fin_rel"] - cand["pos_inicio_rel"] >= 0.9:
        return "obra_completa"

    centro = cand["centro_rel"]

    if centro < 0.15:
        return "presentacion"

    if centro < 0.50:
        return "desarrollo"

    if centro < 0.85:
        return "complicacion_climax"

    return "desenlace"


def etiqueta_posicion(cand):
    etiqueta = cand["capitulo"]

    if cand["n_partes"] > 1:
        etiqueta += f" (parte {cand['parte']}/{cand['n_partes']})"

    return etiqueta


def preparar_obras(candidatos, args, excluir):
    por_libro = defaultdict(list)

    for cand in candidatos:
        por_libro[cand["book_id"]].append(cand)

    obras = []

    for book_id in sorted(por_libro):
        cands = sorted(por_libro[book_id], key=lambda c: c["centro_rel"])
        total = sum(c["n_palabras"] for c in cands)
        tipo, nota = tipo_de_obra(cands, total, args.umbral_novela)

        puntuar_obra(cands)

        elegibles = [
            c for c in cands
            if args.min_aceptable <= c["n_palabras"] <= args.max_aceptable
            and (book_id, c["candidato_id"]) not in excluir
        ]

        obras.append({"book_id": book_id, "cands": cands, "total": total,
                      "tipo": tipo, "nota": nota, "elegibles": elegibles})

    return obras


def buscar_escala(obras, args):
    """Escala (multiplicador de cuotas de novelas) que deja el total mas cerca de --ajustar-a."""
    mejor_escala, mejor_dif = 1.0, None

    for paso in range(1, 801):
        escala = paso * 0.025
        total = sum(cuota_de_obra(o, escala, args) for o in obras)
        dif = abs(total - args.ajustar_a)

        if mejor_dif is None or dif < mejor_dif:
            mejor_escala, mejor_dif = escala, dif

    return round(mejor_escala, 3)


# ----------------------------------------------------------------------------
# Reportes
# ----------------------------------------------------------------------------

def escribir_distribucion(ruta, filas):
    acumulado = defaultdict(lambda: [0, 0])

    for fila in filas:
        for dimension, valor in (
            ("autor", fila["author"]),
            ("obra", f"{fila['title']} ({fila['author']})"),
            ("tipo", fila["tipo"] or "sin_dato"),
            ("genero", fila["genero"] or "sin_dato"),
            ("epoca", fila["epoca"] or "sin_dato"),
            ("idioma_original", fila["idioma_original"] or "sin_dato"),
            ("pais_origen", fila["pais_origen"] or "sin_dato"),
            ("idioma", fila["language"]),
            ("rol_narrativo", fila["narrative_role"]),
        ):
            acumulado[(dimension, valor)][0] += 1
            acumulado[(dimension, valor)][1] += int(fila["n_words"])

    with open(ruta, "w", encoding="utf-8", newline="") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(["dimension", "valor", "fragmentos", "palabras"])

        for (dimension, valor), (n, palabras) in sorted(
            acumulado.items(), key=lambda x: (x[0][0], -x[1][0], x[0][1])
        ):
            escritor.writerow([dimension, valor, n, palabras])


def main():
    parser = argparse.ArgumentParser(
        description="Etapa B (hibrida): zonas por posicion + importancia dentro de cada zona."
    )
    parser.add_argument("--candidatos", type=Path, default=RUTA_CANDIDATOS)
    parser.add_argument("--salida", type=Path, default=RUTA_CORPUS)
    parser.add_argument("--umbral-novela", type=int, default=cfg.UMBRAL_NOVELA,
                        help="palabras desde las cuales una obra sin 'tipo' en el catalogo se trata como novela.")
    parser.add_argument("--fragmentos-cuento", type=int, default=cfg.FRAGMENTOS_CUENTO)
    parser.add_argument("--palabras-por-fragmento", type=int, default=cfg.PALABRAS_POR_FRAGMENTO,
                        help="novelas: un fragmento por cada tantas palabras (antes de la escala).")
    parser.add_argument("--min-novela", type=int, default=cfg.MIN_NOVELA)
    parser.add_argument("--max-novela", type=int, default=cfg.MAX_NOVELA)
    parser.add_argument("--max-cobertura", type=float, default=cfg.MAX_COBERTURA)
    parser.add_argument("--escala", type=float, default=1.0, help="multiplicador de la cuota de las novelas.")
    parser.add_argument("--ajustar-a", type=int, default=None,
                        help="busca la escala que deja el total mas cerca de este numero de fragmentos.")
    parser.add_argument("--min-aceptable", type=int, default=cfg.MIN_ACEPTABLE)
    parser.add_argument("--max-aceptable", type=int, default=cfg.MAX_ACEPTABLE)
    parser.add_argument("--objetivo-min", type=int, default=300)
    parser.add_argument("--objetivo-max", type=int, default=500)

    args = parser.parse_args()

    if not args.candidatos.exists():
        print(f"No encontre {args.candidatos}. Ejecuta primero scripts/03_limpiar_segmentar.py")
        return

    candidatos = leer_candidatos(args.candidatos)

    if not candidatos:
        print("El archivo de candidatos esta vacio.")
        return

    incluir, excluir = leer_overrides(RUTA_OVERRIDES)
    obras = preparar_obras(candidatos, args, excluir)

    escala = buscar_escala(obras, args) if args.ajustar_a else args.escala

    filas_corpus = []
    reporte = []
    contador = 1

    for obra in obras:
        cuota = cuota_de_obra(obra, escala, args)
        vacias = 0
        elegidos = []

        if obra["elegibles"]:
            elegidos, vacias = elegir_por_zonas(obra["elegibles"], zonas_de_obra(obra["tipo"], max(cuota, 1)))

        ids = {c["candidato_id"] for c, _ in elegidos}
        manuales = [
            (c, "manual") for c in obra["cands"]
            if (obra["book_id"], c["candidato_id"]) in incluir and c["candidato_id"] not in ids
        ]

        nota = obra["nota"]

        if not obra["elegibles"]:
            nota = (nota + "; " if nota else "") + "SIN candidatos elegibles (revisar rangos o segmentacion)"
        elif len(obra["elegibles"]) < cuota:
            nota = (nota + "; " if nota else "") + "menos elegibles que la cuota"

        if vacias:
            nota = (nota + "; " if nota else "") + f"{vacias} zona(s) sin candidatos propios"

        if manuales:
            nota = (nota + "; " if nota else "") + f"{len(manuales)} incluido(s) manualmente"

        for cand, zona in sorted(elegidos + manuales, key=lambda x: x[0]["centro_rel"]):
            filas_corpus.append({
                "fragment_id": f"F{contador:04d}",
                "book_id": cand["book_id"],
                "title": cand["title"],
                "author": cand["author"],
                "chapter_position": etiqueta_posicion(cand),
                "text": cand["text"],
                "language": cand["language"],
                "source": cand["source"],
                "url": cand["url"],
                "tipo": obra["tipo"],
                "genero": cand.get("genero", ""),
                "epoca": cand.get("epoca", ""),
                "idioma_original": cand.get("idioma_original", ""),
                "pais_origen": cand.get("pais_origen", ""),
                "position_rel": f"{cand['centro_rel']:.4f}",
                "n_words": cand["n_palabras"],
                "narrative_role": "manual" if zona == "manual" else rol_narrativo(cand),
                "zone": zona,
                "importance": cand.get("importancia", ""),
                "winning_query": cand.get("consulta_ganadora", ""),
                "candidato_id": cand["candidato_id"],
            })
            contador += 1

        primero = obra["cands"][0]
        reporte.append({
            "book_id": obra["book_id"],
            "title": primero["title"],
            "author": primero["author"],
            "tipo": obra["tipo"],
            "palabras_totales": obra["total"],
            "candidatos": len(obra["cands"]),
            "elegibles": len(obra["elegibles"]),
            "cuota": cuota,
            "seleccionados": len(elegidos) + len(manuales),
            "zonas_vacias": vacias,
            "nota": nota,
        })

    args.salida.parent.mkdir(parents=True, exist_ok=True)
    CARPETA_SELECCION.mkdir(parents=True, exist_ok=True)

    with open(args.salida, "w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=CAMPOS_CORPUS, delimiter="\t")
        escritor.writeheader()
        escritor.writerows(filas_corpus)

    with open(CARPETA_SELECCION / "reporte_seleccion.csv", "w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=CAMPOS_REPORTE_SELECCION)
        escritor.writeheader()
        escritor.writerows(reporte)

    escribir_distribucion(CARPETA_SELECCION / "reporte_distribucion.csv", filas_corpus)

    config = {
        "parametros": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
        "pesos": cfg.PESOS,
        "consultas_de_seleccion": cfg.CONSULTAS_IMPORTANTES,
        "escala_usada": escala,
        "huella_sha1_candidatos": huella_archivo(args.candidatos),
        "overrides": {"incluir": len(incluir), "excluir": len(excluir)},
        "total_fragmentos": len(filas_corpus),
    }

    with open(CARPETA_SELECCION / "config_seleccion.json", "w", encoding="utf-8") as archivo:
        json.dump(config, archivo, ensure_ascii=False, indent=2)

    total = len(filas_corpus)
    palabras = sum(int(f["n_words"]) for f in filas_corpus)
    autores = len({f["author"] for f in filas_corpus})

    print(f"Obras en candidatos: {len(obras)} | con fragmentos: {len({f['book_id'] for f in filas_corpus})} | autores: {autores}")
    print(f"Fragmentos seleccionados: {total} ({palabras} palabras) | escala de cuotas: {escala}")
    print(f"Corpus crudo: {args.salida}")
    print(f"Reportes: {CARPETA_SELECCION}/")

    if total < args.objetivo_min:
        print(f"\nAVISO: {total} < {args.objetivo_min}. Opciones: subir --escala o --max-novela, "
              f"agregar obras, o usar --ajustar-a {args.objetivo_min}.")
    elif total > args.objetivo_max:
        print(f"\nAVISO: {total} > {args.objetivo_max}. Opciones: bajar --escala o --max-novela, "
              f"o usar --ajustar-a {args.objetivo_max}.")

    problemas = [r for r in reporte if "SIN candidatos" in r["nota"] or "sin candidatos propios" in r["nota"]]

    if problemas:
        print("\nObras por revisar:")
        for r in problemas:
            print(f" - {r['book_id']}: {r['nota']}")

    if total:
        autor_top, n_top = Counter(f["author"] for f in filas_corpus).most_common(1)[0]
        print(f"\nAutor con mas fragmentos: {autor_top} ({n_top}, {100 * n_top / total:.0f} %)")


if __name__ == "__main__":
    main()
