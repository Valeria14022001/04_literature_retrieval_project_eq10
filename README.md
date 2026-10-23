# Recuperación de literatura — Equipo 10

Proyecto de Procesamiento de Lenguaje Natural, etapa 1.

**Juárez Ramírez Roxana y Reynoso Ortega Valeria**

El sistema recupera los diez fragmentos literarios más similares a una consulta libre en español mediante VSM y similitud coseno. Se eligen título o texto, unigramas o bigramas y frecuencia, binaria o TF-IDF.

Esta es la entrega mínima con corpus y artefactos ya generados. **Para probar el buscador no es necesario repetir la preparación ni la auditoría.** Solo se conservan como procesos independientes las validaciones de auditoría del corpus. Se retiraron verificadores separados de normalización, matrices y evaluación, pruebas automatizadas y archivos redundantes; se mantienen controles básicos de funcionamiento dentro de los programas.

## 1. Instalar y ejecutar

Entorno observado: Python 3.14.3, spaCy 3.8.16 y es_core_news_sm 3.8.0. Las versiones directas están en [requirements.txt](requirements.txt). No se ha probado una instalación limpia en todos los sistemas.

En PowerShell, desde la raíz:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\Activate.ps1
```

Si no puedes activar el entorno, utiliza `.\.venv\Scripts\python.exe` en lugar de `python`. No hace falta modificar la política de PowerShell. Se necesita internet para instalar dependencias y el modelo; la búsqueda posterior utiliza archivos locales.

```powershell
python scripts/09_recuperar_fragmentos.py --consulta "descripción de una tormenta" --contenido texto --ngrama 1 --representacion tfidf --salida resultados/consultas/tormenta
```

| Argumento | Valores |
|---|---|
| `--consulta` | Consulta libre en español |
| `--contenido` | `titulo` o `texto` |
| `--ngrama` | `1` o `2` |
| `--representacion` | `frecuencia`, `binaria` o `tfidf` |
| `--query-id` | ID opcional, Q01 por defecto |
| `--salida` | Carpeta para guardar la consulta; se sobrescribe si se repite |

Se muestran diez resultados con score y se guardan rankings.tsv, consulta.json e informe.html con los textos originales completos. Para visualizar el HTML, abrirlo en un navegador. GitHub puede mostrar su código.

La consulta usa las mismas funciones y versión del modelo que el corpus; se aplica transform sobre el vocabulario e IDF existentes, sin volver a ajustarlos. Los empates se resuelven por ID. Si hay menos de diez coincidencias positivas se completa con ceros y se avisa: **un cero no acredita relevancia**. No hay traducción automática del inglés.

## 2. Estructura mínima

```text
scripts/                     Preparación, auditoría y funciones principales
datos/
  literature_raw_corpus.tsv
  literature_normalized_corpus.tsv
  normalizacion.json         Metadatos generados automáticamente por 05
  fuentes_epub/              33 TXT para cotejar la correspondencia
auditoria/                   Resumen, fichas, cambios y pendientes
vectorizacion/
  matrices/                  12 matrices dispersas NPZ
  vectorizadores/            12 modelos joblib
  ids_documentos.tsv
  manifiesto.json
benchmark/
  queries.tsv
  qrels.tsv
  juicios_evidencia.tsv
resultados/
  <configuracion>/rankings.tsv
  <configuracion>/metricas.tsv
  metricas_por_consulta.tsv
  comparacion_configuraciones.tsv
  metricas_por_nivel.tsv
  diagnostico_consultas.json
  analisis_errores.json
  resumen.json
informes/informe_final.pdf
catalogo_libros.csv
```

El corpus activo es la v2: 300 fragmentos, 33 obras y 27 autores. Se preservaron sus textos y los juicios del benchmark al reorganizar esta entrega. Los IDs históricos F0197/F0198 fueron sustituidos por F0301/F0302; no se mezclan versiones.

## 3. Flujo desde las fuentes

Los EPUB originales deben proporcionarse en fuentes/epub/. No están incluidos. Sí se entregan los TXT estructurados y su índice de procedencia para cotejar el corpus. No se afirma reconstrucción desde fuentes ausentes.

```powershell
python scripts/00_generar_catalogo_libros.py
python scripts/01_extraer_epub.py
python scripts/02_limpiar_segmentar.py
python scripts/03_seleccionar_fragmentos.py --ajustar-a 300
```

La selección requiere suficiente material elegible. Estos comandos generan un corpus y pueden sobrescribir entradas y derivados. **No ejecutarlos para probar el corpus ya entregado.** Un corpus nuevo requiere nuevas anotaciones de benchmark, aunque repita algunos IDs.

Auditoría opcional del corpus generado:

```powershell
python scripts/04_auditar_corpus.py
python scripts/04b_auditar_coherencia.py
```

Las salidas nuevas quedan en auditoria/revision_tecnica/ y auditoria/revision_narrativa/, sin sustituir las evidencias históricas. Los patrones narrativos son alertas, no decisiones automáticas de calidad literaria. Consultar [auditoria/LEEME.md](auditoria/LEEME.md).

## 4. Normalizar y vectorizar

Estos pasos son opcionales al utilizar los archivos incluidos y sobrescriben sus derivados:

```powershell
python scripts/05_normalizar_corpus.py
python scripts/07_vectorizar_corpus.py
```

El script 05 tokeniza, etiqueta POS y lematiza títulos y textos con español. Conserva originales y añade columnas normalizadas. Excluye DET, ADP, CCONJ, SCONJ y PRON, puntuación y símbolos aislados; regulariza espacios y separadores de diálogo en la vista de análisis. Conserva tildes y negaciones adverbiales. DET abarca otros determinantes además de artículos.

05 genera normalizacion.json automáticamente; 07 incorpora esos metadatos al manifiesto. No hace falta ejecutar un validador aparte. El buscador comprueba únicamente compatibilidad de versión/política, hashes de entrada, IDs y dimensiones; no vuelve a procesar todo el corpus al iniciar.

Se generan las doce combinaciones de contenido, ngramas y representación. Los tokens normalizados se conservan por separación de espacios. TF-IDF usa suavizado IDF y norma L2. Los bigramas pueden cruzar oraciones o unir términos tras filtrar categorías, pero no cruzan documentos.

| Contenido | Unigramas | Bigramas |
|---|---|---|
| Título | 300 × 63 | 300 × 32 |
| Texto | 300 × 18542 | 300 × 132153 |

Los 75 títulos normalizados de una palabra no tienen bigramas; no se elimina ninguna fila. Las matrices se guardan dispersas y el manifiesto relaciona sus archivos y versiones con el corpus. Los joblib son artefactos propios; no cargar modelos de procedencia desconocida.

## 5. Benchmark y evaluación

```powershell
python scripts/10_evaluar_benchmark.py
```

El comando lee [queries.tsv](benchmark/queries.tsv) y [qrels.tsv](benchmark/qrels.tsv) directamente. No necesita congeladores ni verificadores externos. Conserva controles básicos de formato, IDs, quince consultas, cinco por nivel y 10–15 positivos con grados 1/2 por consulta. La copia entregada tiene 190 juicios.

Se generan 180 rankings y 1800 posiciones para doce configuraciones en resultados/. Se calculan P@10, R@10, F1@10, MRR truncado al Top-10 y nDCG@10 con ganancia 2^relevancia−1. F1 se calcula por consulta antes de promediar. Para usar otra carpeta de entrada o salida:

```powershell
python scripts/10_evaluar_benchmark.py --benchmark benchmark --salida resultados
```

El programa registra hashes de las entradas en su resumen para identificar la ejecución. Si cambian consultas o qrels, volver a ejecutar todas las configuraciones y conservar la versión previa antes de sobrescribir resultados. Los juicios no se generan a partir de los scores del buscador.

**Evaluación provisional:** las etiquetas son asistidas por IA mediante ventanas y contexto local, con validación humana pendiente. Los ausentes de qrels son no juzgados, aunque se computen como 0 por la convención del ejercicio. Se identificaron pertinentes omitidos; por ello, las métricas no representan precisión o recall reales sobre todos los fragmentos. La dificultad es de diseño y las consultas son informadas por el corpus, no una evaluación externa independiente.

En este experimento, frecuencia con unigramas del texto obtuvo nDCG medio 0.1768; la baseline TF-IDF obtuvo 0.1497. No se afirma superioridad universal. Las configuraciones de título no encontraron coincidencias positivas; sus métricas no nulas provienen del desempate de ceros. En bigramas del texto, once consultas por configuración tampoco tuvieron coincidencias positivas.

## 6. Evidencias e informe

- [Informe final](informes/informe_final.pdf): nombres del equipo, método, resultados, cinco mejores y cinco peores casos relativos y limitaciones.
- [Resumen técnico](auditoria/resumen_tecnico.json).
- [Fichas narrativas históricas](auditoria/evaluaciones_narrativas.csv).
- [Cambios por fragmento](auditoria/cambios.tsv) e [incidencias pendientes](auditoria/incidencias_pendientes.tsv).
- [Justificaciones de relevancia](benchmark/juicios_evidencia.tsv).
- [Comparación de configuraciones](resultados/comparacion_configuraciones.tsv).

Se conservaron los 300 fragmentos por decisión del equipo, incluidas incidencias conocidas. La auditoría y las correcciones no equivalen a aprobación narrativa final ni validación humana del benchmark. Esas limitaciones siguen vigentes en esta entrega simplificada.
