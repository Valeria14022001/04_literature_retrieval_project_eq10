# Guía de ejecución y evaluación docente
## Equipo 10 · Etapa 1

Juárez Ramírez Roxana y Reynoso Ortega Valeria

## Descarga del proyecto

Repositorio: https://github.com/Valeria14022001/04_literature_retrieval_project_eq10

Los programas se descargan desde GitHub y se ejecutan desde la computadora, la ruta recomendada utiliza Windows y PowerShell (entorno de desarrollo). Entorno de referencia Python 3.14.3.

```powershell
git clone https://github.com/Valeria14022001/04_literature_retrieval_project_eq10.git
cd 04_literature_retrieval_project_eq10
git rev-parse HEAD
```

Conservar el identificador mostrado por el último comando para registrar qué revisión se evaluó. 

Ejecutar desde la raíz del repositorio, una línea a la vez:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

```powershell
.\.venv\Scripts\python.exe -c "import spacy, sklearn; n=spacy.load('es_core_news_sm'); print(spacy.__version__, n.meta['version'], sklearn.__version__)"
```

Versiones esperadas: spaCy 3.8.16, modelo 3.8.0 y scikit-learn 1.9.1. 

<!-- PAGEBREAK -->

## Buscador de fragmentos

Corpus y doce representaciones vectoriales ya integradas. Ejecutar:

```powershell
.\.venv\Scripts\python.exe scripts/09_recuperar_fragmentos.py --consulta "descripción de una tormenta" --contenido texto --ngrama 1 --representacion tfidf --query-id revision01 --salida revision_docente/tormenta
```

Resultado esperado: 
- Consulta normalizada
- Diez posiciones con score
- ID
- Título 
- Autor. 

Se crean estos archivos en revision_docente/tormenta/:

- rankings.tsv: las diez posiciones, con query_id, document_id, rank y score.
- consulta.json: configuración, consulta normalizada, avisos y resultados completos.
- informe.html: visor de resultados con el texto original completo de cada fragmento.

Abrir revision_docente/tormenta/informe.html desde el explorador de archivos con un navegador y desplegar “Leer fragmento original completo”. GitHub puede mostrar el código del HTML en lugar del visor.

## Parámetros manuales

*Solo consultas en español.

- --consulta: "---".
- --contenido: texto
- --ngrama: 1 (unigramas); 2 (bigramas)
- --representacion: frecuencia, binaria o tfidf.
- --query-id: revisionZZ (ZZ -> número de revisión)
- --salida: revision_docente/Carpeta_única_para_la_consulta #Se sobrescribe si se repite el nombre

Para comparar representaciones con la misma consulta:

```powershell
.\.venv\Scripts\python.exe scripts/09_recuperar_fragmentos.py --consulta "descripción de una tormenta" --contenido texto --ngrama 1 --representacion frecuencia --query-id DOCENTE01 --salida revision_docente/tormenta_frecuencia

## Revisión

- Diez IDs distintos: Los empates se ordenan por el id
- Rangos del 1 al 10: Cuando no se completan los 10 empates positivos, se complenta con scores de 0 
- Scores en orden descendente. 

<!-- PAGEBREAK -->

## Reproducir la evaluación del benchmark

Ejecutar: 

```powershell
.\.venv\Scripts\python.exe scripts/10_evaluar_benchmark.py --benchmark benchmark --salida revision_docente/benchmark
```

La carpeta de salida conserva los resultados entregados; el programa imprime las métricas de las doce configuraciones.

## Archivos

- Corpus: conformado por 300 fragmentos de 33 obras y 27 autores.
- Benchmark: 15 consultas.
- Configuraciones: contenido; ngramas; representaciones (2x2x3 = 12)
- Salida: Rankings de diez documentos.

## Archivos para revisar

Dentro de revision_docente/benchmark/:

- resumen.json: cantidades, hashes de entradas y casos mejores/peores relativos.
- comparacion_configuraciones.tsv: promedios de las doce configuraciones.
- metricas_por_consulta.tsv: 180 filas de métricas, una por consulta y configuración.
- metricas_por_nivel.tsv: comparación por nivel de dificultad.
- texto_1_tfidf/rankings.tsv: 150 posiciones de la baseline.
- texto_1_tfidf/metricas.tsv: métricas de sus quince consultas.
- diagnostico_consultas.json: coincidencias positivas, no juzgados y avisos.

Los TSV se pueden abrir en una hoja de cálculo, indicando UTF-8 y tabulación como separador. Para cada una de las otras once configuraciones también se generan rankings.tsv y metricas.tsv.

<!-- PAGEBREAK -->

## Revisar el proceso y las evidencias

Abrir informes/informe_final.pdf para revisar el método, los resultados y el análisis.

<!-- PAGEBREAK -->

## Resumen

- La descarga contiene los corpus, matrices, vectorizadores, consultas y qrels.
- El script 09 genera diez posiciones y un visor con textos completos.
- Se compararon al menos dos configuraciones con la misma consulta.
- El script 10 produce doce configuraciones, 180 rankings y 1800 posiciones.
- Se cotejaron las métricas de referencia y se leyeron casos recuperados.
- Se revisaron las evidencias de auditoría y las limitaciones del benchmark.