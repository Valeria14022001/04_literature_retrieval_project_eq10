# Recuperación de literatura, etapa 1 — Equipo 10

**Juárez Ramírez Roxana y Reynoso Ortega Valeria**

El sistema recupera los diez fragmentos literarios más similares a una consulta libre en español mediante VSM y similitud coseno. Se eligen título o texto, unigramas o bigramas y frecuencia, binaria o TF-IDF.

## 1. Instalar y ejecutar

Entorno observado: Python 3.14.3, spaCy 3.8.16 y es_core_news_sm 3.8.0. En PowerShell, desde la raíz:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\Activate.ps1
```

Alternativa: utilizar `.\.venv\Scripts\python.exe` en lugar de `python`. 

```powershell
python scripts/09_recuperar_fragmentos.py --consulta "descripción de una tormenta" --contenido texto --ngrama 1 --representacion tfidf --salida resultados/consultas/tormenta
```

| Argumento | Valores |
|---|---|
| `--consulta` | Consulta libre en español |
| `--contenido` | `texto` |
| `--ngrama` | `1` o `2` |
| `--representacion` | `frecuencia`, `binaria` o `tfidf` |
| `--query-id` | ID opcional, Q01 por defecto |
| `--salida` | Carpeta para guardar la consulta; se sobrescribe si se repite |

Se muestran diez resultados con score y se guardan rankings.tsv, consulta.json e informe.html con los textos originales completos. Para visualizar el HTML, abrir en navegador.

La consulta usa las mismas funciones y versión del modelo que el corpus; se aplica transform sobre el vocabulario e IDF existentes, sin volver a ajustarlos. Los empates se resuelven por ID. Si hay menos de diez coincidencias positivas se completa con ceros y se avisa.

## 2. Estructura

```text
scripts/                     
datos/
  literature_raw_corpus.tsv
  literature_normalized_corpus.tsv
  normalizacion.json         Metadatos generados por 05
  fuentes_epub/              33 TXT 
auditoria/                   Resumen, fichas, cambios y pendientes
vectorizacion/
  matrices/                  
  vectorizadores/            
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

## 3. Flujo desde las fuentes

Los EPUB originales deben proporcionarse en fuentes/epub/. 

```powershell
python scripts/00_generar_catalogo_libros.py
python scripts/01_extraer_epub.py
python scripts/02_limpiar_segmentar.py
python scripts/03_seleccionar_fragmentos.py --ajustar-a 300
```

La selección requiere suficiente material elegible, se genera un corpus y pueden sobrescribir entradas y derivados. **No ejecutarlos para no sobrescribir.**

Auditoría:

```powershell
python scripts/04_auditar_corpus.py
python scripts/04b_auditar_coherencia.py
```

Las salidas nuevas quedan en auditoria/revision_tecnica/ y auditoria/revision_narrativa/, sin sustituir las evidencias históricas. Los patrones narrativos son alertas, no decisiones automáticas de calidad literaria. Consultar [auditoria/LEEME.md](auditoria/LEEME.md).

## 4. Normalizar y vectorizar

**No ejecutar para no sobrescribir**

```powershell
python scripts/05_normalizar_corpus.py
python scripts/07_vectorizar_corpus.py
```

Se generan las doce combinaciones de contenido, ngramas y representación. Los tokens normalizados se conservan por separación de espacios. TF-IDF usa suavizado IDF y norma L2. 

| Contenido | Unigramas | Bigramas |
|---|---|---|
| Texto | 300 × 18542 | 300 × 132153 |

Las matrices se guardan dispersas y el manifiesto relaciona sus archivos y versiones con el corpus. Los joblib originales deben conservarse.

## 5. Benchmark y evaluación

```powershell
python scripts/10_evaluar_benchmark.py
```

La copia que ya está integrada tiene 190 juicios. Se generan 180 rankings y 1800 posiciones para doce configuraciones en resultados/. Se calculan P@10, R@10, F1@10, MRR truncado al Top-10 y nDCG@10 con ganancia 2^relevancia−1. F1 se calcula por consulta antes de promediar. 

Para usar otra carpeta de entrada o salida:

```powershell
python scripts/10_evaluar_benchmark.py --benchmark benchmark --salida resultados
```