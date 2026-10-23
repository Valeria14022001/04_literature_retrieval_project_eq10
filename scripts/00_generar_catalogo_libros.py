from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET
import csv
import fitz
import re
import unicodedata


CARPETAS = [
    Path("fuentes/epub"),
    Path("fuentes/pdf"),
]

RUTA_CATALOGO = Path("catalogo_libros.csv")


ATRIBUTOS_DEFAULT = {
    "tipo": "novela",
    "genero": "narrativo",
    "epoca": "sxix/sxx",
    "idioma_original": "es",
    "pais_origen": "n/a",
    "url": "n/a",
}

ALIAS_METADATA = {
    "tipo": ("tipo", "type"),
    "genero": ("genero", "genre", "subject"),
    "epoca": ("epoca", "period", "era", "temporal"),
    "idioma_original": ("idioma_original", "original_language", "language", "lang"),
    "pais_origen": ("pais_origen", "pais", "country", "country_of_origin", "spatial"),
    "url": ("url", "source", "relation", "identifier"),
}


def normalizar_clave(clave):
    clave = clave.rsplit("}", 1)[-1].rsplit(":", 1)[-1]
    clave = unicodedata.normalize("NFKD", clave.lower())
    return "".join(c for c in clave if not unicodedata.combining(c)).replace("-", "_").replace(" ", "_")


def extraer_atributos(metadata):
    valores = {}
    for clave, valor in metadata:
        valor = limpiar_texto(valor)
        if valor:
            valores.setdefault(normalizar_clave(clave), []).append(valor)
    atributos = {}
    for campo, aliases in ALIAS_METADATA.items():
        for alias in aliases:
            candidatos = valores.get(alias, [])
            if campo == "url":
                candidatos = [v for v in candidatos if re.match(r"https?://", v, re.I)]
            if candidatos:
                atributos[campo] = candidatos[0]
                break
    return atributos


def pares_metadata_xml(raiz):
    for elemento in raiz.iter():
        clave = elemento.attrib.get("name") or elemento.attrib.get("property") or elemento.tag
        valor = elemento.attrib.get("content") or " ".join(elemento.itertext())
        yield clave, valor
        for atributo, contenido in elemento.attrib.items():
            yield atributo, contenido


def normalizar_nombre_archivo(nombre):
    nombre = Path(nombre).stem
    nombre = nombre.replace("_", " ").replace("-", " ")
    nombre = re.sub(r"\s+", " ", nombre).strip()
    return nombre.title()


def limpiar_texto(texto):
    if not texto:
        return ""

    texto = texto.replace("\n", " ").replace("\r", " ")
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def obtener_ruta_opf(epub):
    try:
        contenido = epub.read("META-INF/container.xml")
        raiz = ET.fromstring(contenido)
        ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
        rootfile = raiz.find(".//c:rootfile", ns)

        if rootfile is not None:
            return rootfile.attrib.get("full-path")
    except Exception:
        return None

    return None


def extraer_metadata_epub(ruta_epub):
    titulo = ""
    autor = ""
    atributos = {}

    try:
        with ZipFile(ruta_epub, "r") as epub:
            ruta_opf = obtener_ruta_opf(epub)

            if not ruta_opf:
                return titulo, autor, atributos

            contenido = epub.read(ruta_opf)
            raiz = ET.fromstring(contenido)

            ns = {
                "dc": "http://purl.org/dc/elements/1.1/"
            }

            atributos = extraer_atributos(pares_metadata_xml(raiz))

            titulo_elemento = raiz.find(".//dc:title", ns)
            autor_elemento = raiz.find(".//dc:creator", ns)

            if titulo_elemento is not None and titulo_elemento.text:
                titulo = limpiar_texto(titulo_elemento.text)

            if autor_elemento is not None and autor_elemento.text:
                autor = limpiar_texto(autor_elemento.text)

    except Exception:
        pass

    return titulo, autor, atributos


def extraer_metadata_pdf(ruta_pdf):
    titulo = ""
    autor = ""
    atributos = {}

    try:
        with fitz.open(ruta_pdf) as documento:
            metadata = documento.metadata or {}
            titulo = limpiar_texto(metadata.get("title", ""))
            autor = limpiar_texto(metadata.get("author", ""))
            pares = list(metadata.items())
            xmp = documento.get_xml_metadata()
            if xmp:
                try:
                    pares.extend(pares_metadata_xml(ET.fromstring(xmp)))
                except ET.ParseError:
                    pass
            atributos = extraer_atributos(pares)

    except Exception:
        pass

    return titulo, autor, atributos


def leer_catalogo_existente():
    if not RUTA_CATALOGO.exists():
        return {}

    registros = {}

    with open(RUTA_CATALOGO, "r", encoding="utf-8", newline="") as archivo:
        lector = csv.DictReader(archivo)

        for fila in lector:
            archivo_original = fila.get("archivo_original", "").strip()

            if archivo_original:
                registros[archivo_original] = fila

    return registros


def generar_catalogo():
    registros_existentes = leer_catalogo_existente()
    registros_finales = dict(registros_existentes)

    for carpeta in CARPETAS:
        if not carpeta.exists():
            continue

        for ruta in sorted(carpeta.iterdir()):
            if ruta.suffix.lower() not in [".epub", ".pdf"]:
                continue

            archivo_original = ruta.name

            formato = ruta.suffix.lower().replace(".", "")

            if formato == "epub":
                titulo, autor, atributos = extraer_metadata_epub(ruta)
            else:
                titulo, autor, atributos = extraer_metadata_pdf(ruta)

            if archivo_original in registros_finales:
                fila = registros_finales[archivo_original]
                for campo in ATRIBUTOS_DEFAULT:
                    if not (fila.get(campo) or "").strip():
                        fila[campo] = atributos.get(campo, "")
                continue

            revisar = "no"

            if not titulo:
                titulo = normalizar_nombre_archivo(ruta.name)
                revisar = "si"

            if not autor:
                autor = "Anonimo"
                revisar = "si"

            registros_finales[archivo_original] = {
                "archivo_original": archivo_original,
                "formato": formato,
                "titulo": titulo,
                "autor": autor,
                "fuente": "Elejandria",
                "revisar": revisar,
                **atributos,
            }

    campos = ["archivo_original", "formato", "titulo", "autor", "fuente", "revisar", *ATRIBUTOS_DEFAULT]

    with open(RUTA_CATALOGO, "w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=campos)
        escritor.writeheader()

        for archivo_original in sorted(registros_finales):
            fila = registros_finales[archivo_original]
            escritor.writerow({
                "archivo_original": fila.get("archivo_original", ""),
                "formato": fila.get("formato", ""),
                "titulo": fila.get("titulo", ""),
                "autor": fila.get("autor", ""),
                "fuente": fila.get("fuente", "Elejandria"),
                "revisar": fila.get("revisar", "si"),
                **{
                    campo: (fila.get(campo) or "").strip() or defecto
                    for campo, defecto in ATRIBUTOS_DEFAULT.items()
                },
            })

    print(f"Catalogo generado/actualizado: {RUTA_CATALOGO}")
    print(f"Libros registrados: {len(registros_finales)}")

    revisar = [fila for fila in registros_finales.values() if fila.get("revisar") == "si"]

    if revisar:
        print()
        print("Libros que necesitan revision manual:")
        for fila in revisar:
            print(f" - {fila['archivo_original']} | titulo: {fila['titulo']} | autor: {fila['autor']}")


if __name__ == "__main__":
    generar_catalogo()