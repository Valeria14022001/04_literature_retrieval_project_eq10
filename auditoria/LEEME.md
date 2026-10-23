# Auditoría conservada en la entrega mínima

Las evidencias ya están generadas; no es necesario repetir esta fase para consultar o evaluar el sistema.

| Archivo | Qué representa |
|---|---|
| resumen_tecnico.json | Auditoría automática posterior de la v2: longitud, duplicados y correspondencia |
| evaluaciones_narrativas.csv | Revisión histórica de los 300 fragmentos de la v1, asistida por IA |
| cambios.tsv | Mapa de la transformación a v2 y de sustituciones de IDs |
| incidencias_pendientes.tsv | Seguimiento de los 42 casos graves históricos |

La revisión narrativa inicial cubrió 107 candidatos y luego los otros 193 fragmentos. Se puntuaron inicio, final, contexto, continuidad e integridad de 0 a 2. Integridad es también criterio independiente de rechazo. No se exige autonomía absoluta de cada pasaje ni se considera la suma una medida universal de calidad literaria.

Se corrigieron capitulares, separadores, residuos de etiquetas, encabezados y límites. De los 42 casos graves históricos se resolvió la causa técnica señalada en 15; 27 mantienen reparación parcial o cotejo pendiente. Las notas históricas no se transfieren automáticamente a los textos nuevos. Se conservan 17 excepciones por encima de 1300 palabras para evitar cortes innecesarios.

La v2 tiene 300 fragmentos. F0197/F0198 eran preliminares y se sustituyeron por ficción de las mismas obras con IDs F0301/F0302. Los defectos ya presentes en EPUB no se repararon inventando lecturas. Algunos metadatos del catálogo son genéricos y no se presentan como verificados. Las interpretaciones narrativas y los juicios de relevancia no equivalen a validación humana.

Para volver a generar alertas desde la raíz:

```powershell
python scripts/04_auditar_corpus.py
python scripts/04b_auditar_coherencia.py
```

Las salidas quedan en revision_tecnica/ y revision_narrativa/ dentro de esta carpeta. Se coteja el corpus con los 33 TXT estructurados incluidos en datos/fuentes_epub/. Los EPUB originales no están incluidos. La versión mínima no entrega los respaldos extensos, informes redundantes o scripts de verificación de otras fases: su retirada no convierte los pendientes en problemas resueltos.

Algunos campos de estas evidencias conservan rutas históricas del equipo original. Son procedencia, no dependencias de ejecución. El respaldo completo anterior a esta simplificación se conserva localmente fuera del repositorio.
