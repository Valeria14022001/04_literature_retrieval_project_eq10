from pathlib import Path
import argparse
import csv
import hashlib
import re
import statistics
import unicodedata


CARPETAS_ENTRADA = [
    Path("datos/fuentes_epub"),
    Path("datos/fuentes_epub/pdf"),
]

CARPETA_SALIDA = Path("datos/candidatos")
RUTA_CANDIDATOS = CARPETA_SALIDA / "candidatos.tsv"
RUTA_REPORTE = CARPETA_SALIDA / "reporte_segmentacion.csv"
RUTA_CATALOGO = Path("catalogo_libros.csv")

FUENTE_DEFAULT = "Elejandria"
IDIOMA = "es"

MIN_PALABRAS = 700          
MAX_PALABRAS = 1300         
OBJETIVO_PALABRAS = 1000    # tamano al que apunta la particion de capitulos largos
MIN_OBRA = 200              
MAX_PARRAFO = 400           
PENALIZACION_CORTE_EN_ORACION = 150  # preferir cortar entre parrafos

CAMPOS_EXTRA_CATALOGO = ["tipo", "genero", "epoca", "idioma_original", "pais_origen", "url"]

AUTORES_ESPECIALES = {}

def quitar_acentos(texto):
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in texto if not unicodedata.combining(c))


def normalizar_slug(nombre):
    nombre = Path(nombre).stem.lower()
    nombre = quitar_acentos(nombre)
    nombre = re.sub(r"[^\w\s-]", "", nombre, flags=re.UNICODE)
    nombre = re.sub(r"\s+", "_", nombre.strip())
    return nombre[:120] or "libro"


def titulo_desde_slug(slug):
    partes = slug.replace("_", " ").replace("-", " ").split()
    palabras_menores = {"de", "del", "la", "las", "el", "los", "y", "en", "un", "una"}
    salida = []

    for i, palabra in enumerate(partes):
        if i > 0 and palabra in palabras_menores:
            salida.append(palabra)
        else:
            salida.append(palabra.capitalize())

    return " ".join(salida).strip() or "Sin titulo"


def autor_desde_slug(slug_autor):
    if slug_autor in AUTORES_ESPECIALES:
        return AUTORES_ESPECIALES[slug_autor]

    partes = slug_autor.split("_")

    if len(partes) == 2:
        return f"{partes[1].capitalize()} {partes[0].capitalize()}"

    return " ".join(p.capitalize() for p in partes) or "Anonimo"


def cargar_catalogo():
    """Lee catalogo_libros.csv. Las columnas tipo/genero/epoca/url son opcionales."""
    catalogo = {}

    if not RUTA_CATALOGO.exists():
        return catalogo

    with open(RUTA_CATALOGO, "r", encoding="utf-8", newline="") as archivo:
        lector = csv.DictReader(archivo)

        for fila in lector:
            archivo_original = (fila.get("archivo_original") or "").strip()
            titulo = (fila.get("titulo") or "").strip()
            autor = (fila.get("autor") or "").strip() or "Anonimo"
            fuente = (fila.get("fuente") or FUENTE_DEFAULT).strip() or FUENTE_DEFAULT

            if not archivo_original or not titulo:
                continue

            datos = {"titulo": titulo, "autor": autor, "fuente": fuente}

            for campo in CAMPOS_EXTRA_CATALOGO:
                datos[campo] = (fila.get(campo) or "").strip()

            catalogo[normalizar_slug(archivo_original) + ".txt"] = datos

    return catalogo


def metadata_desde_nombre(ruta_txt, catalogo):
    """Devuelve (metadata, esta_en_catalogo)."""
    nombre = ruta_txt.name

    if nombre in catalogo:
        return catalogo[nombre], True

    slug = ruta_txt.stem

    if "-" in slug:
        slug_titulo, slug_autor = slug.rsplit("-", 1)
        titulo = titulo_desde_slug(slug_titulo)
        autor = autor_desde_slug(slug_autor)
    else:
        titulo = titulo_desde_slug(slug)
        autor = "Anonimo"

    return {
        "titulo": titulo,
        "autor": autor,
        "fuente": FUENTE_DEFAULT,
        **{campo: "" for campo in CAMPOS_EXTRA_CATALOGO},
    }, False


def contar_palabras(texto):
    return len(texto.split())


def normalizar_para_hash(texto):
    texto = texto.lower().strip()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"\s+", " ", texto)
    texto = re.sub(r"[^a-z0-9 ]", "", texto)
    return texto


def hash_fragmento(texto):
    return hashlib.sha1(normalizar_para_hash(texto).encode("utf-8")).hexdigest()


def cortar_finales_editoriales(texto):
    patrones_corte = [
        r"¡Gracias por leer este libro",
        r"Gracias por leer este libro",
        r"Descubre nuestra colección",
        r"Document Outline",
        r"Facilitado por Librodot",
        r"Facilitado por la Biblioteca Virtual Miguel de Cervantes",
        r"Súmese como voluntario",
        r"Si se advierte algún tipo de error",
        r"www\.biblioteca\.org\.ar",
        r"En nuestra web encontrarás muchos más libros",
    ]

    posiciones = []

    for patron in patrones_corte:
        match = re.search(patron, texto, flags=re.IGNORECASE)
        if match and match.start() > 100:
            posiciones.append(match.start())

    for match in re.finditer(r"(?im)^\s*Glosario\s*$", texto):
        if match.start() > len(texto) * 0.55:
            posiciones.append(match.start())

    if posiciones:
        texto = texto[:min(posiciones)]

    return texto


def es_linea_basura(linea):
    limpia = linea.strip()
    normal = quitar_acentos(limpia).lower()

    if not limpia:
        return False

    # Un número aislado puede ser narrativo, una fecha o una numeración.
    # La paginación requiere evidencia estructural, no se elimina aquí.

    basura_exacta = {
        "cover",
        "indice",
        "índice",
        "copyright",
        "all rights reserved",
        "english",
        "francais",
        "français",
        "polski",
        "русский",
        "українська",
        "日本語",
    }

    if normal in basura_exacta:
        return True

    if len(limpia.split()) > 25:
        return False

    # Una mención narrativa a «corrección» o «transcripción» no es un
    # crédito editorial. Exigir etiqueta al inicio, dos puntos y un valor.
    # Sin esa estructura, conservar la línea para evitar pérdida literaria.
    if re.match(
        r"^(?:correccion|transcripcion)(?:\s+(?:de estilo|de textos|ortografica))?\s*:\s*\S",
        normal,
    ):
        return True

    basura_contiene = [
        "libro descargado en",
        "www.elejandria.com",
        "tu sitio web de obras de dominio",
        "esperamos que lo disfrute",
        "publicado:",
        "fuente:",
        "traduccion:",
        "traducción:",
        "edicion original",
        "edición original",
        "categoria:",
        "categoría:",
        "literatura y ficcion >",
        "literatura y ficción >",
        "libro publicado por elejandria",
        "estrictamente para uso personal",
        "no puede ser utilizado con fines comerciales",
        "la propiedad de esta obra",
        "reservados todos los derechos",
        "permitido el uso sin fines comerciales",
        "súmese como voluntario",
        "sumese como voluntario",
    ]

    return any(fragmento in normal for fragmento in basura_contiene)


def limpiar_lineas_basura(texto):
    lineas_limpias = []

    for linea in texto.splitlines():
        linea = linea.strip()

        if es_linea_basura(linea):
            continue

        lineas_limpias.append(linea)

    return "\n".join(lineas_limpias)


def reparar_guiones_y_espacios(texto):
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    texto = texto.replace("\xa0", " ")
    texto = texto.replace("–", "—")

    texto = re.sub(
        r"([A-Za-zÁÉÍÓÚÜÑáéíóúüñ])-\s*\n\s*([A-Za-zÁÉÍÓÚÜÑáéíóúüñ])",
        r"\1\2",
        texto
    )

    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)

    return texto.strip()


def es_titulo_mayusculas(linea):
    linea = linea.strip()

    if not (4 <= len(linea) <= 90):
        return False

    if any(signo in linea for signo in ["www.", "http", "@"]):
        return False

    if linea.endswith((".", ",", ";", ":", "?", "!", "¿", "¡")):
        return False

    letras = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", linea)

    if len(letras) < 4:
        return False

    mayusculas = re.findall(r"[A-ZÁÉÍÓÚÜÑ]", linea)
    proporcion = len(mayusculas) / max(len(letras), 1)

    palabras = linea.split()

    if len(palabras) > 12:
        return False

    return proporcion >= 0.80


def es_encabezado(linea):
    linea = linea.strip()

    if not linea:
        return False

    if es_titulo_mayusculas(linea):
        return True

    patrones = [
        r"^(PRIMERA|SEGUNDA|TERCERA|CUARTA|QUINTA|SEXTA|SÉPTIMA|SEPTIMA)\s+PARTE$",
        r"^PARTE\s+[IVXLCDM]+$",
        r"^CAP[ÍI]TULO\s+([0-9]+|[IVXLCDM]+|PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|S[ÉE]PTIMO|OCTAVO|NOVENO|D[ÉE]CIMO|UND[ÉE]CIMO|DUOD[ÉE]CIMO).*$",
        r"^Cap[íi]tulo\s+[0-9]+$",
        r"^\d{1,3}\.\s+[A-ZÁÉÍÓÚÜÑ].{3,90}$",
    ]

    if linea.isupper() and re.fullmatch(r"[IVXLCDM]{1,8}", linea):
        return True
    return any(re.match(patron, linea, flags=re.IGNORECASE) for patron in patrones)


def buscar_inicio_narrativo(texto):
    candidatos = []

    patrones_fuertes = [
        r"(?im)^\s*(PRIMERA|SEGUNDA|TERCERA|CUARTA|QUINTA|SEXTA|SÉPTIMA|SEPTIMA)\s+PARTE\s*$",
        r"(?im)^\s*PARTE\s+[IVXLCDM]+\s*$",
        r"(?im)^\s*CAP[ÍI]TULO\s+([0-9]+|[IVXLCDM]+|PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|S[ÉE]PTIMO|OCTAVO|NOVENO|D[ÉE]CIMO|UND[ÉE]CIMO|DUOD[ÉE]CIMO).*$",
        r"(?im)^\s*Cap[íi]tulo\s+[0-9]+\s*$",
        r"(?im)^\s*\d{1,3}\.\s+[A-ZÁÉÍÓÚÜÑ].{3,90}$",
    ]

    for patron in patrones_fuertes:
        for match in re.finditer(patron, texto):
            candidatos.append(match.start())

    for match in re.finditer(r"(?m)^\s*[IVXLCDM]{1,8}\s*$", texto):
        siguiente = texto[match.end(): match.end() + 180]
        lineas = [l.strip() for l in siguiente.splitlines() if l.strip()]

        if lineas and len(lineas[0]) >= 3 and not es_linea_basura(lineas[0]):
            candidatos.append(match.start())

    if not candidatos:
        intro = re.search(r"(?im)^\s*INTRODUCCI[ÓO]N\s*$", texto)

        if intro:
            return intro.start()

        prologo = re.search(r"(?im)^\s*PR[ÓO]LOGO\s*$", texto)

        if prologo:
            return prologo.end()

        return 0

    candidatos = sorted(set(candidatos))

    indice = re.search(r"(?im)^\s*[ÍI]NDICE\s*$", texto)

    if indice and indice.start() < 5000:
        limite = indice.start() + 300
        posteriores = [pos for pos in candidatos if pos > limite]

        if posteriores:
            return posteriores[0]

    return candidatos[0]


def recortar_inicio(texto):
    inicio = buscar_inicio_narrativo(texto)

    if inicio > 0:
        return texto[inicio:].strip()

    lineas = texto.splitlines()
    salida = []
    saltando_inicio = True

    for linea in lineas:
        if saltando_inicio and es_linea_basura(linea):
            continue

        saltando_inicio = False
        salida.append(linea)

    return "\n".join(salida).strip()


def reconstruir_parrafos(texto):
    lineas = [linea.strip() for linea in texto.splitlines()]
    parrafos = []
    actual = []

    for indice, linea in enumerate(lineas):
        if not linea:
            if actual:
                parrafos.append(" ".join(actual).strip())
                actual = []
            continue

        numeral_entre_texto = (
            es_numeral_romano_suelto(linea)
            and indice > 0 and indice + 1 < len(lineas)
            and bool(lineas[indice - 1]) and bool(lineas[indice + 1])
        )
        if es_encabezado(linea) and not numeral_entre_texto:
            if actual:
                parrafos.append(" ".join(actual).strip())
                actual = []
            parrafos.append(linea)
            continue

        actual.append(linea)

    if actual:
        parrafos.append(" ".join(actual).strip())

    texto = "\n\n".join(p for p in parrafos if p)
    texto = re.sub(r"\s+([,.;:!?])", r"\1", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)

    return texto.strip()


def limpiar_texto(texto):
    texto = cortar_finales_editoriales(texto)
    texto = reparar_guiones_y_espacios(texto)
    texto = limpiar_lineas_basura(texto)
    texto = recortar_inicio(texto)
    texto = reconstruir_parrafos(texto)

    return texto.strip()


# ----------------------------------------------------------------------------
# Limpieza de cabeceras sueltas dentro de un fragmento (heredada)
# ----------------------------------------------------------------------------

def es_numeral_romano_suelto(texto):
    return bool(re.fullmatch(r"[IVXLCDM]{1,8}", texto.strip()))


def es_encabezado_de_capitulo_suelto(texto):
    texto = texto.strip()

    patrones = [
        r"^Cap[íi]tulo\s+[IVXLCDM0-9]+\.?$",
        r"^CAP[ÍI]TULO\s+[IVXLCDM0-9]+\.?$",
        r"^\d{1,3}\.\s+.{3,90}\.?$",
    ]

    return any(re.match(patron, texto, flags=re.IGNORECASE) for patron in patrones)


def es_titulo_suelto_de_fragmento(texto):
    texto = texto.strip()

    if "\n" in texto:
        return False

    if not (3 <= len(texto) <= 120):
        return False

    if contar_palabras(texto) > 14:
        return False

    if texto.endswith((",", ";", ":")):
        return False

    if es_numeral_romano_suelto(texto):
        return True

    if es_encabezado_de_capitulo_suelto(texto):
        return True

    letras = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", texto)

    if not letras:
        return False

    mayusculas = re.findall(r"[A-ZÁÉÍÓÚÜÑ]", texto)

    return len(mayusculas) / max(len(letras), 1) >= 0.80


def quitar_subtitulo_pegado(parrafo):
    parrafo = parrafo.strip()

    # [CAMBIO] Solo se conserva el patron generico; se quitaron los patrones
    # especificos de Moby Dick / Verne del proyecto anterior.
    patrones = [
        r"^Cap[íi]tulo\s+(?=(El|La|Los|Las|Un|Una|Al|Cuando|Después|Tres|Pasaron|Sería|Así)\b)",
    ]

    for patron in patrones:
        parrafo = re.sub(patron, "", parrafo, flags=re.IGNORECASE).strip()

    return parrafo


def quitar_cabecera_fragmento(fragmento):
    # Los títulos internos, versos y numerales forman parte de la estructura.
    # Los encabezados iniciales de capítulo ya se separan en construir_capitulos.
    # No borrar aquí líneas por mayúsculas ni subtítulos inferidos por su forma.
    return fragmento.strip()


# ----------------------------------------------------------------------------
# ETAPA A (nuevo): capitulos -> piezas -> candidatos con posicion relativa
# ----------------------------------------------------------------------------

def dividir_por_encabezados(texto):
    bloques = []
    actual = []

    for parrafo in texto.split("\n\n"):
        parrafo = parrafo.strip()

        if not parrafo:
            continue

        primera_linea = parrafo.splitlines()[0].strip()

        if es_encabezado(primera_linea) and actual:
            bloques.append("\n\n".join(actual).strip())
            actual = [parrafo]
        else:
            actual.append(parrafo)

    if actual:
        bloques.append("\n\n".join(actual).strip())

    return bloques


def es_parrafo_encabezado(parrafo):
    return contar_palabras(parrafo) <= 14 and es_encabezado(parrafo.splitlines()[0])


def es_numeracion(texto):
    """'CAPITULO IV', 'IV', '12', 'Capitulo 3.' ..."""
    return bool(re.fullmatch(
        r"(CAP[ÍI]TULO\s+)?([0-9]{1,3}|[IVXLCDM]{1,8})\.?",
        texto.strip(),
        flags=re.IGNORECASE,
    ))


def es_subtitulo(texto):
    """Linea corta, sin puntuacion final, que acompana a una numeracion de capitulo."""
    texto = texto.strip()

    return (
        "\n" not in texto
        and 2 <= len(texto.split()) <= 10
        and not texto.endswith((".", "!", "?", "…", ",", ";", ":"))
        and not texto.startswith(("—", "-", "«", "“", "\"", "¿", "¡"))
    )


def normalizar_titulo(texto):
    texto = quitar_acentos(texto).lower()
    texto = re.sub(r"[^a-z0-9 ]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def quitar_titulo_repetido(texto, titulo):
    """Quita el titulo del libro cuando aparece repetido en los primeros parrafos."""
    titulo_norm = normalizar_titulo(titulo)
    salida = []

    for indice, parrafo in enumerate(texto.split("\n\n")):
        norm = normalizar_titulo(parrafo)

        if (
            indice < 3
            and parrafo.strip()
            and contar_palabras(parrafo) <= 14
            and len(norm) >= 6
            and (norm == titulo_norm or norm in titulo_norm)
        ):
            continue

        salida.append(parrafo)

    return "\n\n".join(salida).strip()


def separar_encabezado(bloque):
    """Separa los parrafos iniciales que son encabezado (hasta 3) del cuerpo."""
    parrafos = [p.strip() for p in bloque.split("\n\n") if p.strip()]
    encabezados = []

    while parrafos and len(encabezados) < 3 and es_parrafo_encabezado(parrafos[0]):
        encabezados.append(parrafos.pop(0))

    # [NUEVO] numeracion seguida de un subtitulo en formato normal:
    # "CAPITULO I" + "El nacimiento del heroe" -> "CAPITULO I. El nacimiento del heroe"
    if (
        encabezados
        and es_numeracion(encabezados[-1])
        and parrafos
        and es_subtitulo(parrafos[0])
        and not es_encabezado(parrafos[0])
    ):
        encabezados[-1] = f"{encabezados[-1]}. {parrafos.pop(0)}"

    return " - ".join(encabezados), "\n\n".join(parrafos)


def construir_capitulos(texto):
    """
    Devuelve una lista de capitulos:
      {"indice", "etiqueta", "texto", "palabras", "offset"}
    offset = palabras del texto limpio que hay antes del capitulo.
    """
    capitulos = []
    etiqueta_pendiente = ""
    offset = 0

    for bloque in dividir_por_encabezados(texto):
        palabras_bloque = contar_palabras(bloque)
        etiqueta, cuerpo = separar_encabezado(bloque)

        if etiqueta_pendiente:
            etiqueta = f"{etiqueta_pendiente} - {etiqueta}" if etiqueta else etiqueta_pendiente
            etiqueta_pendiente = ""

        if not cuerpo.strip():
            # bloque que solo tenia encabezado (p. ej. "CAPITULO I" y luego el
            # titulo en otra linea): su etiqueta se pasa al bloque siguiente
            etiqueta_pendiente = etiqueta
            offset += palabras_bloque
            continue

        indice = len(capitulos) + 1
        palabras_cuerpo = contar_palabras(cuerpo)

        capitulos.append({
            "indice": indice,
            "etiqueta": etiqueta or f"seccion_{indice}",
            "texto": cuerpo,
            "palabras": palabras_cuerpo,
            "offset": offset + (palabras_bloque - palabras_cuerpo),
        })
        offset += palabras_bloque

    return capitulos


def unidades_de_texto(texto):
    """
    Divide un texto en unidades de corte: (texto, palabras, separador_previo).
    Los parrafos muy largos se dividen en oraciones para poder cortarlos.
    """
    unidades = []

    for parrafo in (p.strip() for p in texto.split("\n\n")):
        if not parrafo:
            continue

        n = contar_palabras(parrafo)

        if n <= MAX_PARRAFO:
            unidades.append((parrafo, n, "\n\n"))
            continue

        # Respetar iniciales y abreviaturas: el punto de K. no termina
        # necesariamente la oración. Solo es un corte auxiliar de párrafo largo.
        from fuentes_estructuradas import safe_sentence_spans
        oraciones = [parrafo[a:b] for a,b in safe_sentence_spans(parrafo)]

        for i, oracion in enumerate(oraciones):
            unidades.append((oracion, contar_palabras(oracion), "\n\n" if i == 0 else " "))

    return unidades


def unir_unidades(unidades):
    salida = ""

    for texto, _, separador in unidades:
        if salida:
            salida += separador
        salida += texto

    return salida


def numero_de_partes(n_palabras, min_p, max_p, objetivo):
    """
    Cuantas partes de tamano parecido conviene para un capitulo de n_palabras.
    Si no existe una division con todas las partes dentro de [min_p, max_p],
    se prefiere NO dividir y el fragmento queda marcado como fuera de rango.
    """
    if n_palabras <= max_p:
        return 1

    n = max(1, int(n_palabras / objetivo + 0.5))

    while n_palabras / n > max_p:
        n += 1

    while n > 1 and n_palabras / n < min_p:
        n -= 1

    return n


def partir_balanceado(unidades, n_partes):
    """Reparte las unidades en n_partes de tamano parecido, cortando donde se pueda entre parrafos."""
    if n_partes <= 1 or len(unidades) < n_partes:
        return [unidades]

    total = sum(u[1] for u in unidades)
    acumulado = []
    suma = 0

    for _, n, _ in unidades:
        suma += n
        acumulado.append(suma)

    cortes = []
    previo = 0

    for k in range(1, n_partes):
        ideal = k * total / n_partes
        mejor = None
        mejor_costo = None

        # corte "antes de la unidad i": palabras previas = acumulado[i - 1]
        for i in range(previo + 1, len(unidades) - (n_partes - k) + 1):
            costo = abs(acumulado[i - 1] - ideal)

            if unidades[i][2] != "\n\n":
                costo += PENALIZACION_CORTE_EN_ORACION

            if mejor_costo is None or costo < mejor_costo:
                mejor, mejor_costo = i, costo

        cortes.append(mejor)
        previo = mejor

    partes = []
    inicio = 0

    for corte in cortes + [len(unidades)]:
        partes.append(unidades[inicio:corte])
        inicio = corte

    return partes


def piezas_desde_capitulos(capitulos, min_p, max_p, objetivo):
    """Un capitulo largo se convierte en varias piezas balanceadas; los demas, en una."""
    piezas = []

    for cap in capitulos:
        n_partes = numero_de_partes(cap["palabras"], min_p, max_p, objetivo)

        if n_partes == 1:
            piezas.append({
                "indice_cap": cap["indice"],
                "etiqueta": cap["etiqueta"],
                "parte": 1,
                "n_partes": 1,
                "texto": cap["texto"],
                "palabras": cap["palabras"],
                "ini": cap["offset"],
                "fin": cap["offset"] + cap["palabras"],
            })
            continue

        partes = partir_balanceado(unidades_de_texto(cap["texto"]), n_partes)
        recorrido = cap["offset"]

        for numero, unidades in enumerate(partes, start=1):
            texto = unir_unidades(unidades)
            palabras = contar_palabras(texto)

            piezas.append({
                "indice_cap": cap["indice"],
                "etiqueta": cap["etiqueta"],
                "parte": numero,
                "n_partes": len(partes),
                "texto": texto,
                "palabras": palabras,
                "ini": recorrido,
                "fin": recorrido + palabras,
            })
            recorrido += palabras

    return piezas


def palabras_de_grupo(grupo):
    return sum(p["palabras"] for p in grupo)


def unir_cortas(piezas, min_p, max_p):
    """
    Junta piezas consecutivas hasta alcanzar min_p sin pasar de max_p.
    Un grupo que no logra el minimo se absorbe en el anterior si cabe;
    si no, queda como fragmento corto (se marca en estado_rango).
    """
    grupos = []
    acumulado = []

    for pieza in piezas:
        if acumulado:
            if palabras_de_grupo(acumulado) + pieza["palabras"] <= max_p:
                acumulado.append(pieza)

                if palabras_de_grupo(acumulado) >= min_p:
                    grupos.append(acumulado)
                    acumulado = []
            else:
                grupos.append(acumulado)
                acumulado = []

                if pieza["palabras"] >= min_p:
                    grupos.append([pieza])
                else:
                    acumulado = [pieza]
        else:
            if pieza["palabras"] >= min_p:
                grupos.append([pieza])
            else:
                acumulado = [pieza]

    if acumulado:
        grupos.append(acumulado)

    # absorber grupos cortos en el anterior cuando cabe
    resultado = []

    for grupo in grupos:
        if (
            palabras_de_grupo(grupo) < min_p
            and resultado
            and palabras_de_grupo(resultado[-1]) + palabras_de_grupo(grupo) <= max_p
        ):
            resultado[-1] = resultado[-1] + grupo
        else:
            resultado.append(grupo)

    return resultado


def etiqueta_de_grupo(grupo):
    etiquetas = []

    for pieza in grupo:
        if not etiquetas or etiquetas[-1] != pieza["etiqueta"]:
            etiquetas.append(pieza["etiqueta"])

    if len(etiquetas) == 1:
        return etiquetas[0]

    if len(etiquetas) == 2:
        return f"{etiquetas[0]} + {etiquetas[1]}"

    return f"{etiquetas[0]} ... {etiquetas[-1]}"


def estado_rango(n_palabras, min_p, max_p):
    if n_palabras < min_p:
        return "corto"

    if n_palabras > max_p:
        return "largo"

    return "en_rango"


def compactar_para_tsv(texto):
    # csv.DictWriter entrecomilla correctamente las celdas multilínea.
    # Conservar los párrafos es necesario para la revisión literaria.
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    texto = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", texto)
    return re.sub(r"[ \t]+", " ", texto).strip()


def segmentar_libro(texto_limpio, min_p, max_p, objetivo):
    capitulos = construir_capitulos(texto_limpio)
    piezas = piezas_desde_capitulos(capitulos, min_p, max_p, objetivo)
    grupos = unir_cortas(piezas, min_p, max_p)

    return capitulos, grupos


# ----------------------------------------------------------------------------
# Programa principal
# ----------------------------------------------------------------------------

CAMPOS_TSV = [
    "candidato_id", "book_id", "title", "author",
    "tipo", "genero", "epoca", "idioma_original", "pais_origen",
    "capitulo", "parte", "n_partes", "capitulos_unidos",
    "pos_inicio_rel", "pos_fin_rel", "centro_rel",
    "n_palabras", "estado_rango",
    "language", "source", "url", "archivo_origen",
    "text",
]

CAMPOS_REPORTE = [
    "archivo_origen", "book_id", "estado", "detalle", "palabras_limpias",
    "capitulos_detectados", "mediana_palabras_capitulo",
    "candidatos", "en_rango", "cortos", "largos", "duplicados_omitidos",
]


def leer_txts_entrada():
    rutas = []

    for carpeta in CARPETAS_ENTRADA:
        if carpeta.exists():
            rutas.extend(sorted(carpeta.glob("*.txt")))

    return rutas


def fila_reporte(ruta_txt, estado, detalle, **extra):
    fila = {campo: "" for campo in CAMPOS_REPORTE}
    fila.update({
        "archivo_origen": ruta_txt.name,
        "book_id": ruta_txt.stem,
        "estado": estado,
        "detalle": detalle,
    })
    fila.update(extra)
    return fila


def main():
    parser = argparse.ArgumentParser(
        description="Etapa A: limpia y segmenta libros en fragmentos candidatos con posicion relativa."
    )
    parser.add_argument("--reiniciar", action="store_true",
                        help="(compatibilidad) la salida siempre se reescribe, no hay nada que acumular.")
    parser.add_argument("--min-palabras", type=int, default=MIN_PALABRAS)
    parser.add_argument("--max-palabras", type=int, default=MAX_PALABRAS)
    parser.add_argument("--objetivo", type=int, default=OBJETIVO_PALABRAS,
                        help="tamano al que apunta la particion de capitulos largos.")
    parser.add_argument("--solo-en-rango", action="store_true",
                        help="guarda solo candidatos dentro de [min, max]; por defecto se guardan todos con su estado_rango.")
    parser.add_argument("--incluir-no-catalogados", action="store_true",
                        help="procesa tambien los .txt que no aparecen en catalogo_libros.csv.")

    args = parser.parse_args()

    if not (args.min_palabras <= args.objetivo <= args.max_palabras):
        print("ERROR: se requiere min-palabras <= objetivo <= max-palabras.")
        return

    catalogo = cargar_catalogo()
    rutas_txt = leer_txts_entrada()

    if not rutas_txt:
        print("No encontre archivos .txt en datos/fuentes_epub ni datos/fuentes_epub/pdf.")
        return

    CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)

    filas = []
    reporte = []
    hashes = set()
    contador = 1

    for ruta_txt in rutas_txt:
        datos, en_catalogo = metadata_desde_nombre(ruta_txt, catalogo)

        if catalogo and not en_catalogo and not args.incluir_no_catalogados:
            reporte.append(fila_reporte(ruta_txt, "omitido", "no esta en catalogo_libros.csv"))
            continue

        texto_original = ruta_txt.read_text(encoding="utf-8", errors="ignore")
        texto_limpio = quitar_titulo_repetido(limpiar_texto(texto_original), datos["titulo"])
        palabras_limpias = contar_palabras(texto_limpio)

        if palabras_limpias < MIN_OBRA:
            reporte.append(fila_reporte(
                ruta_txt, "descartado",
                f"texto limpio demasiado corto: {palabras_limpias} palabras",
                palabras_limpias=palabras_limpias,
            ))
            continue

        capitulos, grupos = segmentar_libro(
            texto_limpio, args.min_palabras, args.max_palabras, args.objetivo
        )

        filas_libro = []
        duplicados = 0

        for grupo in grupos:
            texto = "\n\n".join(p["texto"] for p in grupo)
            texto = quitar_cabecera_fragmento(texto)
            n_palabras = contar_palabras(texto)

            if n_palabras == 0:
                continue

            huella = hash_fragmento(texto)

            if huella in hashes:
                duplicados += 1
                continue

            hashes.add(huella)

            ini = grupo[0]["ini"]
            fin = grupo[-1]["fin"]
            total = max(palabras_limpias, 1)

            if len(grupo) == 1:
                parte, n_partes = grupo[0]["parte"], grupo[0]["n_partes"]
            else:
                parte, n_partes = 1, 1

            estado = estado_rango(n_palabras, args.min_palabras, args.max_palabras)

            if args.solo_en_rango and estado != "en_rango":
                continue

            filas_libro.append({
                "book_id": ruta_txt.stem,
                "title": datos["titulo"],
                "author": datos["autor"],
                "tipo": datos.get("tipo", ""),
                "genero": datos.get("genero", ""),
                "epoca": datos.get("epoca", ""),
                "idioma_original": datos.get("idioma_original", ""),
                "pais_origen": datos.get("pais_origen", ""),
                "capitulo": etiqueta_de_grupo(grupo),
                "parte": parte,
                "n_partes": n_partes,
                "capitulos_unidos": len({p["indice_cap"] for p in grupo}),
                "pos_inicio_rel": round(min(ini / total, 1.0), 4),
                "pos_fin_rel": round(min(fin / total, 1.0), 4),
                "centro_rel": round(min((ini + fin) / 2 / total, 1.0), 4),
                "n_palabras": n_palabras,
                "estado_rango": estado,
                "language": IDIOMA,
                "source": datos["fuente"],
                "url": datos.get("url", ""),
                "archivo_origen": ruta_txt.name,
                "text": compactar_para_tsv(texto),
            })

        if not filas_libro:
            reporte.append(fila_reporte(
                ruta_txt, "descartado", "sin fragmentos validos",
                palabras_limpias=palabras_limpias, duplicados_omitidos=duplicados,
            ))
            continue

        for fila in filas_libro:
            fila["candidato_id"] = f"C{contador:05d}"
            contador += 1

        filas.extend(filas_libro)

        medianas = statistics.median(c["palabras"] for c in capitulos) if capitulos else 0
        detalle = "ok"

        if len(capitulos) <= 1 and palabras_limpias > args.max_palabras:
            detalle = "ok; ALERTA: no se detectaron capitulos, se partio todo el texto"

        reporte.append(fila_reporte(
            ruta_txt, "procesado", detalle,
            palabras_limpias=palabras_limpias,
            capitulos_detectados=len(capitulos),
            mediana_palabras_capitulo=round(medianas),
            candidatos=len(filas_libro),
            en_rango=sum(1 for f in filas_libro if f["estado_rango"] == "en_rango"),
            cortos=sum(1 for f in filas_libro if f["estado_rango"] == "corto"),
            largos=sum(1 for f in filas_libro if f["estado_rango"] == "largo"),
            duplicados_omitidos=duplicados,
        ))

    with open(RUTA_CANDIDATOS, "w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=CAMPOS_TSV, delimiter="\t")
        escritor.writeheader()
        escritor.writerows(filas)

    with open(RUTA_REPORTE, "w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=CAMPOS_REPORTE)
        escritor.writeheader()
        escritor.writerows(reporte)

    procesados = [r for r in reporte if r["estado"] == "procesado"]
    en_rango = sum(1 for f in filas if f["estado_rango"] == "en_rango")

    print(f"Libros TXT revisados: {len(rutas_txt)}")
    print(f"Libros procesados: {len(procesados)}")
    print(f"Candidatos generados: {len(filas)} (en rango: {en_rango}, "
          f"fuera de rango: {len(filas) - en_rango})")
    print(f"Candidatos: {RUTA_CANDIDATOS}")
    print(f"Reporte: {RUTA_REPORTE}")

    pendientes = [r for r in reporte if r["estado"] == "descartado" or "ALERTA" in r["detalle"]]

    if pendientes:
        print()
        print("Descartados o por revisar:")

        for item in pendientes:
            print(f" - {item['archivo_origen']}: {item['detalle']}")

    omitidos = [r for r in reporte if r["estado"] == "omitido"]

    if omitidos:
        print()
        print(f"Omitidos por no estar en el catalogo: {len(omitidos)} "
              f"(usa --incluir-no-catalogados para procesarlos)")


if __name__ == "__main__":
    main()
