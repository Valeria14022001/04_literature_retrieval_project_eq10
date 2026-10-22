from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET
import csv
import fitz
import re
import unicodedata


CARPETAS = [
    Path("descargas_elejandria/epub"),
    Path("descargas_elejandria/pdf"),
]

RUTA_CATALOGO = Path("catalogo_libros.csv")


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

    try:
        with ZipFile(ruta_epub, "r") as epub:
            ruta_opf = obtener_ruta_opf(epub)

            if not ruta_opf:
                return titulo, autor

            contenido = epub.read(ruta_opf)
            raiz = ET.fromstring(contenido)

            ns = {
                "dc": "http://purl.org/dc/elements/1.1/"
            }

            titulo_elemento = raiz.find(".//dc:title", ns)
            autor_elemento = raiz.find(".//dc:creator", ns)

            if titulo_elemento is not None and titulo_elemento.text:
                titulo = limpiar_texto(titulo_elemento.text)

            if autor_elemento is not None and autor_elemento.text:
                autor = limpiar_texto(autor_elemento.text)

    except Exception:
        pass

    return titulo, autor


def extraer_metadata_pdf(ruta_pdf):
    titulo = ""
    autor = ""

    try:
        documento = fitz.open(ruta_pdf)
        metadata = documento.metadata or {}

        titulo = limpiar_texto(metadata.get("title", ""))
        autor = limpiar_texto(metadata.get("author", ""))

        documento.close()

    except Exception:
        pass

    return titulo, autor


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

            if archivo_original in registros_finales:
                continue

            formato = ruta.suffix.lower().replace(".", "")

            if formato == "epub":
                titulo, autor = extraer_metadata_epub(ruta)
            else:
                titulo, autor = extraer_metadata_pdf(ruta)

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
            }

    campos = ["archivo_original", "formato", "titulo", "autor", "fuente", "revisar"]

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