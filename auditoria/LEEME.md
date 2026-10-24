# Auditoría conservada en la entrega mínima

| Archivo | Qué representa |
|---|---|
| resumen_tecnico.json | Auditoría automática posterior de la v2: longitud, duplicados y correspondencia |
| evaluaciones_narrativas.csv | Revisión histórica de los 300 fragmentos de la v1, asistida por IA |
| cambios.tsv | Mapa de la transformación a v2 y de sustituciones de IDs |
| incidencias_pendientes.tsv | Seguimiento de los 42 casos graves históricos |

La revisión narrativa puntuó inicio, final, contexto, continuidad e integridad de 0 a 2. Se corrigieron capitulares, separadores, residuos de etiquetas, encabezados y límites. 

Para volver a generar alertas desde la raíz:

```powershell
python scripts/04_auditar_corpus.py
python scripts/04b_auditar_coherencia.py
```

Las salidas quedan en revision_tecnica/ y revision_narrativa/ dentro de esta carpeta. Se coteja el corpus con los 33 TXT estructurados incluidos en datos/fuentes_epub/. Los EPUB originales no están incluidos. 
