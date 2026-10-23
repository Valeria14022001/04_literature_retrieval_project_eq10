from pathlib import Path
from zipfile import ZipFile
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import re
import unicodedata


CARPETA_ENTRADA = Path("fuentes/epub")
CARPETA_SALIDA = Path("datos/fuentes_epub")


def limpiar_nombre(nombre):
    nombre = nombre.lower()
    nombre = unicodedata.normalize("NFKD", nombre)
    nombre = "".join(c for c in nombre if not unicodedata.combining(c))
    nombre = re.sub(r"[^\w\s-]", "", nombre, flags=re.UNICODE)
    nombre = re.sub(r"\s+", "_", nombre.strip())
    return nombre[:120] or "libro"


def obtener_ruta_opf(epub):
    try:
        contenido = epub.read("META-INF/container.xml")
        raiz = ET.fromstring(contenido)
        namespace = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
        rootfile = raiz.find(".//c:rootfile", namespace)

        if rootfile is not None:
            return rootfile.attrib.get("full-path")
    except Exception:
        return None

    return None


def obtener_archivos_en_orden(epub, ruta_opf):
    if not ruta_opf:
        return []

    try:
        contenido = epub.read(ruta_opf)
        raiz = ET.fromstring(contenido)

        ns = {
            "opf": "http://www.idpf.org/2007/opf"
        }

        carpeta_base = str(Path(ruta_opf).parent)
        if carpeta_base == ".":
            carpeta_base = ""

        manifest = {}
        for item in raiz.findall(".//opf:manifest/opf:item", ns):
            item_id = item.attrib.get("id")
            href = item.attrib.get("href")
            media_type = item.attrib.get("media-type", "")

            if item_id and href and ("html" in media_type or href.endswith((".html", ".xhtml", ".htm"))):
                ruta = str(Path(carpeta_base) / href).replace("\\", "/")
                manifest[item_id] = ruta

        archivos = []
        for itemref in raiz.findall(".//opf:spine/opf:itemref", ns):
            idref = itemref.attrib.get("idref")
            if idref in manifest:
                archivos.append(manifest[idref])

        return archivos

    except Exception:
        return []


def obtener_archivos_html_respaldo(epub):
    archivos = []

    for nombre in epub.namelist():
        nombre_minusculas = nombre.lower()

        if nombre_minusculas.endswith((".html", ".xhtml", ".htm")):
            if "cover" in nombre_minusculas:
                continue
            if "nav" in nombre_minusculas:
                continue
            if "toc" in nombre_minusculas:
                continue

            archivos.append(nombre)

    return sorted(archivos)


def html_a_texto(contenido):
    sopa = BeautifulSoup(contenido, "html.parser")

    for etiqueta in sopa(["script", "style", "head", "nav", "metadata"]):
        etiqueta.decompose()

    # Los cambios de estilo no son límites de palabra ni de párrafo.
    # get_text("\n") dividía palabras alrededor de span/em/a.
    cuerpo = sopa.body or sopa
    bloques = cuerpo.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "pre"])
    bloques = [b for b in bloques if not b.find_parent(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "pre"])]
    textos = []
    for bloque in bloques or [cuerpo]:
        for br in bloque.find_all("br"):
            br.replace_with("\uE000")
        texto = bloque.get_text("", strip=False).replace("\xa0", " ")
        texto = re.sub(r"\s+", " ", texto).replace("\uE000", "\n").strip()
        if texto:
            textos.append(texto)
    return "\n\n".join(textos)


def extraer_epub(ruta_epub):
    'Extrae la vista estructurada; 08_corregir_corpus guarda su procedencia detallada.'
    from fuentes_estructuradas import extract_book
    return extract_book(Path(ruta_epub))['text']


def main():
    CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)

    archivos_epub = sorted(CARPETA_ENTRADA.glob("*.epub"))

    if not archivos_epub:
        print("No encontré archivos EPUB en fuentes/epub")
        return

    for indice, ruta_epub in enumerate(archivos_epub, start=1):
        print(f"[{indice}/{len(archivos_epub)}] Extrayendo EPUB: {ruta_epub.name}")

        texto = extraer_epub(ruta_epub)

        if not texto.strip():
            print("  No se extrajo texto.")
            continue

        nombre_salida = limpiar_nombre(ruta_epub.stem) + ".txt"
        ruta_salida = CARPETA_SALIDA / nombre_salida

        ruta_salida.write_text(texto, encoding="utf-8")

        print(f"  Guardado: {ruta_salida}")
        print(f"  Palabras aproximadas: {len(texto.split())}")


if __name__ == "__main__":
    main()
