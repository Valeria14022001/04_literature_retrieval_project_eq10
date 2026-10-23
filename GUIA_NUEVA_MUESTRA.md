# Guía para construir y utilizar otra muestra literaria

Esta guía permite entender como funciona el proyecto, desde libros EPUB a un corpus auditado, un buscador y una evaluación de recuperación. 

## 1. Qué se va a construir

A partir de las novelas, se obtienen pasajes o fragmentos; cada uno se convierte en un documento recuperable. Después transforma sus títulos y textos en vectores de términos. Una consulta se procesa con la misma normalización y se compara con esos vectores mediante similitud coseno.

El recorrido es:

```text
Libros EPUB y metadatos revisados
    ↓ 00 + 01
Catálogo y textos extraídos de las obras
    ↓ 02
Todos los fragmentos candidatos
    ↓ 03
Muestra seleccionada: corpus sin normalizar
    ↓ 04 + 04b + auditoría manual y correcciones
Corpus auditado
    ↓ 05
Corpus normalizado 
    ↓ 07
12 matrices y 12 vectorizadores
    ↓ 09
Consultas y rankings de diez fragmentos
    ↓ nuevas consultas + nuevos juicios humanos + 10
Comparación de configuraciones y análisis de errores
```

Hay diez programas principales y dos módulos de apoyo: `config_seleccion.py` y `fuentes_estructuradas.py`.

### Conceptos

| Concepto | Significado |
|---|---|
| Ejemplar | Libro completo del que se extraen pasajes. |
| Candidato | Pasaje producido por la segmentación, antes de elegir la muestra. |
| Fragmento/documento | Candidato seleccionado como unidad de recuperación. |
| Corpus sin normalizar | Texto literario de los fragmentos después de la preparación y limpieza; todavía conserva redacción, signos y palabras funcionales. No equivale al archivo EPUB intacto. |
| Corpus normalizado | Vista de análisis que añade términos lematizados y filtrados, conservando las columnas originales. |
| Vectorizador | Modelo que conserva el vocabulario y, en TF-IDF, los pesos aprendidos del corpus. |
| Ranking | Lista ordenada por similitud con una consulta. |
| Qrels | Juicios de relevancia que permiten comparar un ranking con una referencia anotada. |

Se trabajó con textos solo en español. Una obra traducida puede tener otro idioma original, pero el contenido procesado debe estar en español. 

## 2. Preparar una carpeta limpia

En una carpeta nueva copiar código, configuración y dependencias. En PowerShell ejecutar:

```powershell
$proyectoBase = "C:\GitHub\04_literature_retrieval_project_eq10"
$proyectoNuevo = "C:\GitHub\muestra_literaria_nueva"
if (Test-Path -LiteralPath $proyectoNuevo) { throw "La carpeta de destino ya existe. Elige otra carpeta vacía." }
New-Item -ItemType Directory -Path $proyectoNuevo | Out-Null
Copy-Item -LiteralPath "$proyectoBase\scripts" -Destination $proyectoNuevo -Recurse
Copy-Item -LiteralPath "$proyectoBase\requirements.txt" -Destination $proyectoNuevo
Copy-Item -LiteralPath "$proyectoBase\.gitignore" -Destination $proyectoNuevo
Copy-Item -LiteralPath "$proyectoBase\.gitattributes" -Destination $proyectoNuevo
Set-Location $proyectoNuevo
New-Item -ItemType Directory -Force -Path fuentes/epub,datos,benchmark,auditoria,informes | Out-Null
```

La copia de `scripts` puede incluir cachés locales; no son datos de investigación ni se necesitan para ejecutar. No copie `.git` ni el entorno virtual anterior. La carpeta creada todavía no es un repositorio Git: puede inicializarlo al preparar su propia publicación.

**Todos los comandos siguientes se ejecutan desde la raíz de la carpeta nueva**, no desde `scripts`. Varios programas usan rutas relativas al directorio actual. Compruébelo con `Get-Location`.

### Instalar las dependencias

El entorno observado del proyecto es Python 3.14.3. Compruebe que dispone de Python 3.14:

```powershell
py -3.14 --version
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\Activate.ps1
python --version
```

Las versiones del archivo corresponden al entorno de desarrollo. Si PowerShell impide activar el entorno, omita la activación y sustituya `python` por `.\.venv\Scripts\python.exe` en cada comando.

## 3. Estructura que se irá formando

No es necesario crear manualmente todas las subcarpetas: los scripts generan sus salidas.

```text
muestra_literaria_nueva/
├── requirements.txt
├── .gitignore
├── .gitattributes
├── catalogo_libros.csv                 Generado por 00 y revisado por usted
├── fuentes/
│   └── epub/                          EPUB originales de esta muestra
├── scripts/                           Los 12 archivos .py (Python)
├── datos/
│   ├── fuentes_epub/                  TXT extraídos por 01
│   ├── candidatos/
│   │   ├── candidatos.tsv
│   │   └── reporte_segmentacion.csv
│   ├── seleccion/
│   │   ├── reporte_seleccion.csv
│   │   ├── reporte_distribucion.csv
│   │   └── config_seleccion.json
│   ├── overrides_seleccion.csv         Opcional: decisiones explícitas de selección
│   ├── literature_raw_corpus.tsv
│   ├── literature_normalized_corpus.tsv
│   └── normalizacion.json
├── auditoria/
│   ├── revision_tecnica/               Salidas de 04
│   ├── revision_narrativa/             Salidas de 04b
│   └── decisiones_nueva_muestra.csv    Parte de la auditoría manual
├── vectorizacion/
│   ├── matrices/                      12 archivos NPZ
│   ├── vectorizadores/                12 archivos joblib
│   ├── ids_documentos.tsv
│   └── manifiesto.json
├── benchmark/
│   ├── queries.tsv                    Preparación manual
│   ├── qrels.tsv                      Preparación manual
│   └── juicios_evidencia.tsv           Registro recomendado de justificaciones
├── resultados/
│   ├── consultas/                     Ejecuciones individuales de 09
│   ├── titulo_1_frecuencia/           Ejemplo de configuración evaluada
│   │   ├── rankings.tsv
│   │   └── metricas.tsv
│   ├── ...                            Otras 11 configuraciones
│   ├── metricas_por_consulta.tsv
│   ├── comparacion_configuraciones.tsv
│   ├── metricas_por_nivel.tsv
│   ├── diagnostico_consultas.json
│   ├── analisis_errores.json           No lo genera 10: análisis que se debe redactar
│   └── resumen.json
└── informes/                          Informe manual
```

CSV separa columnas por comas y TSV por tabulaciones. Se guarda en UTF-8. Los textos pueden contener saltos de línea dentro de una celda entrecomillada: no se cuentan líneas físicas como documentos ni edite estas tablas con reemplazos de texto indiscriminados. Un lector CSV/TSV reconoce esos campos correctamente.

## 4. Elegir las obras y registrar sus fuentes

Colocar los archivos `.epub` directamente en `fuentes/epub/`. El extractor busca esa extensión en esa carpeta, sin recorrer subcarpetas. Use nombres distintos que sigan siendo distintos al quitar acentos, signos y espacios: esos nombres se convierten en identificadores y nombres TXT. Dos ediciones con nombres que se normalizan igual pueden sobrescribirse. Los scripts no descargan libros, no ejecutan OCR ni resuelven archivos protegidos. La carpeta de EPUB está ignorada por Git en esta entrega por temas de espacio.

Se usaron varias obras para cumplir un mínimo de 300 fragmentos se necesita suficiente texto elegible y diversidad; una prueba pequeña no alcanzará ese tamaño y no debe completarse duplicando pasajes.

## 5. Script 00: generar y corregir el catálogo

```powershell
python scripts/00_generar_catalogo_libros.py
```

**Entrada:** archivos de `fuentes/epub/`; también puede leer metadatos de archivos en `fuentes/pdf/`. Si ya existe `catalogo_libros.csv`, lo lee y conserva sus registros.

**Proceso:** consulta los metadatos internos de cada archivo para obtener título, autor y atributos adicionales. Cuando faltan título o autor utiliza valores de respaldo y marca el registro para revisión. Algunos atributos reciben valores predeterminados, aunque el libro no los haya declarado.

**Salida:** `catalogo_libros.csv`, con las columnas:

```text
archivo_original, formato, titulo, autor, fuente, revisar,
tipo, genero, epoca, idioma_original, pais_origen, url
```

En consola debe aparecer la ruta del catálogo y el número de libros registrados. Puede aparecer una lista de libros para revisión manual.

**Qué debe hacer antes de continuar:** abra el CSV y revise todos los registros, incluso aquellos con `revisar=no`. El programa asigna `Elejandria` como fuente inicial y puede completar valores como `novela`, `narrativo`, `sxix/sxx` o `es`; no son hechos bibliográficos verificados. Corrija esos campos para su colección y sustituya `n/a` por datos comprobados cuando corresponda. `idioma_original` describe la obra original; el texto que procesa esta implementación sigue siendo español.

En `tipo`, utilice `novela`, `novela_corta` o `cuento` para que la selección reconozca el valor. Conserve `archivo_original` exactamente igual al nombre del archivo, incluida su extensión. No renombre las fuentes después de catalogarlas sin actualizar la correspondencia.

**Interpretación importante:** volver a ejecutar 00 no borra las filas de libros retirados y no reemplaza automáticamente los títulos o autores ya existentes. Para una muestra nueva se comienza sin catálogo anterior. Si corrige una fila manualmente, conserve esa versión revisada.

El soporte PDF de este programa es solo de catalogación. La ruta completa documentada aquí utiliza EPUB; 01 no extrae PDF. Para incorporar PDF necesitará una extracción y auditoría adicionales.

## 6. Script 01 y módulo fuentes_estructuradas: extraer texto

```powershell
python scripts/01_extraer_epub.py
```

**Entrada:** los EPUB de `fuentes/epub/`.

**Proceso:** el programa llama a `extract_book` del módulo `fuentes_estructuradas.py`. Este lee el orden de lectura del EPUB, recorre sus documentos HTML y obtiene bloques de texto. Conserva párrafos y evita introducir espacios entre etiquetas en línea que podrían partir palabras. Excluye estructuras reconocidas de portada, navegación y determinadas notas o residuos editoriales. También contiene tratamientos específicos de algunas obras del experimento original; no constituyen una solución general para cualquier edición nueva.

**Salida:** un TXT UTF-8 por obra en `datos/fuentes_epub/`. Por ejemplo, `Mi novela.epub` produce `mi_novela.txt`. En consola se indica cada libro, la ruta de salida y un conteo aproximado de palabras.

`fuentes_estructuradas.py` es una biblioteca, no un paso que deba ejecutar por separado. Incluye funciones de extracción, cortes auxiliares y alineación. Su función de extracción devuelve internamente bloques, exclusiones y procedencia; **el script 01 solo guarda el texto**, no genera un `procedencia.json`. El índice de procedencia de la muestra original no se reconstruye mediante este comando.

**Qué revisar:** abra varios TXT y coteje inicio, mitad y final con sus EPUB. Compruebe orden de capítulos, párrafos, diálogos, tildes, palabras con cursivas y transiciones entre archivos internos. Un total alto de palabras no demuestra una extracción correcta.

Si hay palabras pegadas, capítulos ausentes, notas incorporadas como relato o texto narrativo eliminado, corrija la extracción antes de segmentar. Conserve los EPUB intactos para cotejar. Si cambia el extractor, documente qué regla modificó y vuelva a extraer las obras afectadas.

01 sobrescribe los TXT de igual nombre, pero no retira los de obras que dejó de incluir. La carpeta nueva evita que esos archivos residuales entren después en la muestra.

## 7. Script 02: limpiar y producir todos los candidatos

```powershell
python scripts/02_limpiar_segmentar.py --min-palabras 700 --max-palabras 1300 --objetivo 1000
```

**Entradas:** TXT de `datos/fuentes_epub/` y, si existe, su subcarpeta `pdf/`; además, `catalogo_libros.csv`.

**Proceso:** asocia textos y metadatos, aplica reglas de limpieza editorial, detecta encabezados/capítulos, reconstruye párrafos y divide el texto en pasajes. Busca aproximarse a 1000 palabras dentro del objetivo 700–1300, procurando conservar límites naturales. Puede unir piezas cortas y dividir párrafos extensos. Omite obras cuyo texto limpio queda por debajo de 200 palabras y omite candidatos con una huella ya observada. Esa deduplicación de preparación no sustituye la auditoría posterior.

**Salidas:**

| Archivo | Para qué sirve |
|---|---|
| `datos/candidatos/candidatos.tsv` | Todos los candidatos conservados, con texto, metadatos, capítulo, posiciones, conteo, estado de longitud e ID `C00001`, etc. |
| `datos/candidatos/reporte_segmentacion.csv` | Resumen por obra: procesada, omitida o descartada; capítulos detectados; candidatos cortos, largos y en rango; observaciones. |

La consola debe indicar libros revisados, procesados y candidatos generados. Los resultados dependen de sus obras; no tienen por qué coincidir con la muestra de 300 fragmentos anterior.

**Cómo interpretar:**

- `estado_rango=en_rango`: cumple el objetivo de longitud, pero todavía puede tener un corte narrativo inadecuado.
- `corto` o `largo`: se conserva para revisión, salvo que se active `--solo-en-rango`.
- Aviso de capítulos no detectados: el programa dividió una unidad mayor; revise el resultado y los límites.
- Omitido por catálogo: el TXT no pudo asociarse al catálogo. Revise nombres y metadatos antes de usar `--incluir-no-catalogados`, que permite procesarlo con datos inferidos.
- Posiciones relativas: sitúan aproximadamente el pasaje dentro del texto limpio; no son números de página del EPUB ni coordenadas directas del texto fuente.

**Mantenga desactivado `--solo-en-rango`** si quiere revisar las excepciones sin descartarlas automáticamente. El argumento `--reiniciar` no vacía fuentes ni inicia una colección nueva: es de compatibilidad; las dos salidas se reescriben de todos modos.

Las reglas de limpieza pueden confundir una línea narrativa con un encabezado o residuo. El TXT extraído se conserva para comprobarlo. No considere segura una eliminación únicamente porque haya sido automática.

## 8. Script 03 y config_seleccion: elegir la muestra

```powershell
python scripts/03_seleccionar_fragmentos.py --ajustar-a 300
```

**Entrada:** `datos/candidatos/candidatos.tsv`; configuración de `scripts/config_seleccion.py`; y, opcionalmente, `datos/overrides_seleccion.csv`.

**Proceso:** agrupa candidatos por obra, calcula cuotas, distribuye la elección por zonas de posición y utiliza una puntuación heurística dentro de ellas. Esa puntuación combina vocabulario de situaciones narrativas, centralidad léxica y cercanía a una posición objetivo. No es una valoración humana de importancia literaria ni una auditoría de coherencia.

Por defecto, la configuración reserva dos pasajes por cuento; para novelas utiliza una cuota relacionada con la longitud, límites de cantidad y de cobertura. `--ajustar-a 300` busca una escala de cuotas que se acerque a 300; **no garantiza exactamente 300 ni crea candidatos adicionales**.

**Salidas:**

| Archivo | Contenido e interpretación |
|---|---|
| `datos/literature_raw_corpus.tsv` | Corpus seleccionado. Cada fila recibe un `fragment_id`, como `F0001`. Es la entrada para auditoría y normalización. |
| `datos/seleccion/reporte_seleccion.csv` | Cuota, elegibles y seleccionados por obra; zonas vacías o material insuficiente. |
| `datos/seleccion/reporte_distribucion.csv` | Distribución de la muestra para comprobar concentración y diversidad. |
| `datos/seleccion/config_seleccion.json` | Parámetros, pesos, consultas de selección, escala, huella de candidatos y total producido. |

La consola informa obras, autores, fragmentos, palabras y autor con mayor representación. Si queda por debajo del objetivo, consulte primero las cuotas y los candidatos elegibles; añadir literatura suele ser preferible a forzar pasajes defectuosos.

### La longitud se trata de forma distinta en 02 y 03

02 conserva por defecto candidatos fuera de 700–1300. Sin embargo, **03 solo considera elegibles automáticamente los de 500–1300 palabras**, según su configuración actual. No asuma que todo candidato conservado será seleccionable.

Si desea permitir excepciones largas para revisarlas después, puede ampliar el margen de selección de forma explícita, por ejemplo:

```powershell
python scripts/03_seleccionar_fragmentos.py --ajustar-a 300 --max-aceptable 1600
```

1600 es un ejemplo de margen, no una recomendación universal. La auditoría seguirá marcando los de más de 1300. Justifique cada excepción y evite aumentar el límite solamente para llegar a una cifra.

### Qué contiene config_seleccion.py

Es un módulo importado por 03. No se ejecuta como etapa independiente. Contiene:

- Márgenes de elegibilidad y penalización de pasajes cortos.
- Cuotas por tipo de obra, cobertura máxima y límite por capítulo.
- Zonas de selección para cuentos y novelas.
- Pesos de consultas, centralidad y posición, actualmente 0.5, 0.3 y 0.2.
- Vocabulario genérico de situaciones narrativas y funciones de tokenización para puntuar la selección.

Los argumentos de 03 tienen prioridad sobre sus valores correspondientes. Esta tokenización de selección no es la normalización spaCy de 05. No copie las consultas del benchmark a este módulo: favorecería seleccionar textos precisamente para responder la evaluación.

### Inclusiones o exclusiones explícitas

El CSV opcional `datos/overrides_seleccion.csv` usa las columnas:

```csv
book_id,candidato_id,accion
mi_novela,C00012,incluir
mi_novela,C00025,excluir
```

Son ejemplos de formato: sustituya los IDs por los de sus candidatos. Una inclusión manual puede incorporar un candidato fuera del margen de elegibilidad y alterar el total. Revise el corpus final y no ponga acciones contradictorias para un mismo par. Si regenera candidatos, compruebe esos pares de nuevo.

**No fije aún el benchmark:** 03 vuelve a asignar IDs secuencialmente al regenerar. Un `F0001` de otra ejecución puede contener un pasaje diferente.

## 9. Script 04: auditoría técnica del corpus sin normalizar

```powershell
python scripts/04_auditar_corpus.py
```

Por defecto lee `datos/literature_raw_corpus.tsv`, coteja con `datos/fuentes_epub/` y escribe en `auditoria/revision_tecnica/`. No modifica ni elimina fragmentos.

**Qué comprueba y qué obtiene:**

| Salida | Uso |
|---|---|
| `resumen.json` | Totales, longitudes, coincidencias, alertas, parámetros y hash del corpus auditado. |
| `informe.html` | Vista en navegador con las tablas y un resumen de longitud. |
| `fragmentos.csv` | Palabras calculadas, estado de longitud y hash del texto por fragmento. |
| `duplicados_exactos.csv` | Pares cuyo texto tiene la misma huella SHA-256. |
| `similares.csv` | Pares con coincidencias léxicas o bloques superpuestos que requieren comparación. |
| `alertas.csv` | Metadatos ausentes, IDs repetidos, posiciones inválidas, conteos discordantes y posibles anomalías. |
| `correspondencia.csv` | Resultado de localizar el fragmento en el TXT de la obra. |
| `cobertura.csv` | Número de fragmentos en los tercios inicial, medio y final. |
| `diversidad.csv` | Cantidades y porcentajes por autor, obra, fuente e idioma. |

Abra `informe.html` con un navegador local. Un CSV sin filas de datos puede significar que no se detectaron casos de ese tipo; no es un archivo fallido por estar solo el encabezado.

La similitud aproximada usa secuencias de palabras y medidas como Jaccard, contención y bloque compartido. Los valores predeterminados incluyen ngramas de cinco palabras, similitud 0.8, solapamiento 0.2 y bloque mínimo de 50 palabras. Son umbrales de alerta. Las medidas son sensibles a mayúsculas, tildes y puntuación y no detectan toda paráfrasis. Revise también si una repetición es deliberada en la obra.

### Interpretar la correspondencia

Correspondencia pregunta si el pasaje puede rastrearse hasta el texto extraído de la obra, **no si es temáticamente similar**.

| Estado | Interpretación y siguiente acción |
|---|---|
| Coincidencia literal | La cadena está en la fuente. Aun así, revise que el corte y el contenido sean pertinentes. |
| Solo diferencias de espacios | Coinciden las palabras tras regularizar separadores en una vista auxiliar. Puede deberse a saltos de línea; no exige cambiar la redacción literaria. |
| No localizado; revisar limpieza o extracción | La búsqueda no consiguió demostrar correspondencia. Puede haber encabezados retirados, diferencias de caracteres, una limpieza excesiva o una fuente incorrecta. Compare los textos. |
| Origen ausente | Falta un TXT cuyo nombre base coincida con `book_id`. Corrija el enlace o la fuente. |
| Origen ambiguo | Hay más de un TXT con el mismo nombre base. Identifique la edición correcta. |

Los índices de caracteres, cuando existen, comienzan en cero y el final es exclusivo. Se refieren al archivo fuente utilizado por esa ejecución. No son páginas y dejan de ser válidos si se modifica el TXT.

Que no exista coincidencia literal no obliga a deshacer una limpieza editorial justificada. Lo necesario es comprobar que conserva la narración y registrar las transformaciones. Tampoco dé por correcta una pérdida de contenido por llamarla “limpieza”.

Cobertura por tercios solo indica posiciones representadas; no mide el porcentaje real leído ni demuestra continuidad narrativa. Una obra con dos fragmentos puede no representar los tres tercios sin que eso sea un error automático.

## 10. Script 04b: priorizar la revisión narrativa

```powershell
python scripts/04b_auditar_coherencia.py --contexto 1200
```

**Entradas:** corpus sin normalizar, TXT fuente y candidatos, si están disponibles. `--contexto` expresa caracteres anteriores y posteriores, no palabras.

**Proceso:** inspecciona comienzos y finales, referencias dependientes, diálogo, puntuación, caracteres y posibles transiciones de capítulo. Intenta localizar el pasaje en la fuente para mostrar el contexto inmediato. Puede utilizar coincidencias auxiliares o aproximadas: revise la evidencia y el estado de localización. Si no consigue localizarlo, el contexto puede quedar vacío; no significa que la obra comience o termine allí.

**Salidas en `auditoria/revision_narrativa/`:**

- `resumen.json`: distribución de prioridades, indicadores y localización.
- `fragmentos.json`: texto íntegro, indicios, pasaje fuente y contextos disponibles.
- `revision.csv`: lista con prioridad, indicadores y columnas vacías para decisión y observaciones humanas.
- `informe.html`: fichas desplegables para comparar antes, fragmento y después.

Las prioridades `alta`, `media`, `baja` y `sin_indicios` ordenan la inspección. No equivalen a rechazo, duda, aceptación y perfección. Si no hay párrafos inequívocos, el script usa ventanas de texto o párrafos de la fuente y lo indica.

### Cómo hacer la revisión humana

1. Empiece por prioridad alta y los problemas técnicos graves.
2. Lea el fragmento completo; no decida únicamente por sus primeras o últimas líneas.
3. Lea el contexto anterior y posterior. Si es insuficiente, abra el TXT o el EPUB y amplíelo.
4. Compruebe si el límite pierde una causa esencial, interrumpe una oración o mezcla pasajes.
5. Distinga una dependencia normal de novela de un corte que destruye la unidad local de lectura.
6. Registre puntuaciones, evidencia, decisión y corrección propuesta.
7. Revise una muestra de `sin_indicios`; la ausencia de alertas no demuestra ausencia de problemas. Si encuentra un patrón repetido, amplíe la inspección.

### Rúbrica de 0 a 2

| Criterio | 0: deficiente | 1: dudoso | 2: adecuado |
|---|---|---|---|
| Inicio | Corte interno o dependencia esencial que impide entrar en el pasaje. | Se entiende parcialmente; conviene ampliar contexto. | Entrada razonable para una lectura local. |
| Final | Acción, oración o explicación esencial cortada por la segmentación. | Cierre discutible que requiere comparación. | Cierre local razonable, aunque la historia continúe. |
| Contexto | No se comprende la situación por información perdida en el corte. | Hay referencias ambiguas relevantes. | Se entiende razonablemente sin exigir una historia autónoma. |
| Continuidad | Incoherencia interna o concatenación errónea. | Posible salto o transición poco clara. | Secuencia y referencias internas consistentes. |
| Integridad | Pérdida o alteración grave del texto fuente. | Diferencias cuya naturaleza aún no se resolvió. | Texto preservado o limpieza editorial cotejada y justificada. |

Sume sobre diez solo para estandarizar la revisión. Como convención inicial, un total de 8–10 sin ceros y con integridad 2 puede aceptarse provisionalmente; otros casos se revisan. **Integridad 0 bloquea la aceptación aunque el total sea 8/10. Integridad 1 permanece pendiente.** No mida calidad literaria con esta suma ni reescriba al autor para elevar la puntuación.

Copie `revision.csv` a un registro de trabajo antes de anotar: ejecutar 04b de nuevo reescribe ese archivo. Puede crear `auditoria/decisiones_nueva_muestra.csv` con estas columnas:

```text
version_corpus,fragment_id,inicio,final,contexto,continuidad,integridad,
total,decision,evidencia,accion,revisor,fecha
```

El programa no genera esas puntuaciones ni aplica correcciones automáticamente.

## 11. Corregir y cerrar una versión del corpus

Primero haga una copia fechada del corpus, candidatos y decisiones fuera de los archivos activos. Luego corrija el origen del problema:

| Problema | Dónde intervenir | Qué repetir |
|---|---|---|
| Título, autor o fuente erróneos | Catálogo | 02 → 03 → auditorías. |
| Extracción defectuosa | Extracción o edición fuente comprobada | 01 → 02 → 03 → auditorías. |
| Limpieza elimina narrativa o segmentación corta mal | Reglas de 02, con evidencia | 02 → 03 → auditorías. |
| Candidato inadecuado con alternativa correcta | Selección y overrides | 03 → auditorías. |
| Corrección puntual del corpus | TSV, con herramienta que respete celdas y metadatos | Auditorías; documentar parche porque 03 lo sobrescribirá. |

No invente palabras ni añada transiciones redactadas por usted. Si amplía un fragmento, tome el texto de su fuente y actualice conteo, posición, capítulo y registro de procedencia. Compruebe duplicados y superposición con los demás pasajes.

Para conservar la auditoría previa al cambio, use una nueva carpeta de salida:

```powershell
python scripts/04_auditar_corpus.py --salida auditoria/revision_tecnica_v2
python scripts/04b_auditar_coherencia.py --salida auditoria/revision_narrativa_v2
```

Puede dar por cerrada una versión cuando los problemas graves estén resueltos o identificados expresamente como pendientes, las excepciones tengan justificación y cada decisión pueda vincularse al corpus revisado. No afirme que una muestra nueva está auditada usando las fichas de la muestra anterior.

Una vez cerrado el corpus, deje de regenerar la selección durante la evaluación. Conserve sus IDs y una huella del archivo. Si cambia su contenido, invalida las anotaciones afectadas aunque conserve el mismo identificador.

## 12. Script 05: normalizar para análisis

```powershell
python scripts/05_normalizar_corpus.py
```

**Entrada:** `datos/literature_raw_corpus.tsv`. Requiere encabezados como `fragment_id`, `book_id`, `title`, `author`, `chapter_position`, `text`, `language`, `source` y `url`, además de IDs únicos y no vacíos.

**Proceso:** carga `es_core_news_sm`, prepara espacios y separadores de diálogo en la vista de análisis, tokeniza, etiqueta categorías gramaticales y lematiza títulos y textos. Convierte los lemas a minúsculas y excluye puntuación, símbolos aislados y las categorías DET, ADP, CCONJ, SCONJ y PRON. DET incluye determinantes además de artículos. No aplica otra lista genérica de stopwords; conserva tildes y negaciones adverbiales según el etiquetado.

**Salidas:**

- `datos/literature_normalized_corpus.tsv`: mismas filas e información original, con `title_normalized` y `text_normalized` añadidos.
- `datos/normalizacion.json`: versión del modelo, spaCy, idioma, hashes de entrada y salida, hash de la política y cantidad de fragmentos.

En consola verá cantidad de filas, modelo, campos añadidos, textos normalizados vacíos y un ejemplo. El mensaje “normalizaciones que fallaron” cuenta textos normalizados vacíos; requiere revisar el caso, no demuestra por sí solo un fallo de ejecución.

Una salida normalizada no tiene que parecer prosa natural: puede perder pronombres y conectores por diseño. Para lectura literaria y auditoría use `text`, el TXT o el EPUB, no `text_normalized`.

Opciones útiles: `--entrada`, `--salida`, `--modelo` y `--lote`. Para este flujo mantenga el modelo predeterminado y las rutas estándar. Cambiar solo `--modelo` no adapta automáticamente el buscador. `--crear-demo` genera una muestra sintética y termina: no procesa sus novelas y no sirve como corpus del proyecto.

## 13. Script 07: construir los espacios vectoriales

```powershell
python scripts/07_vectorizar_corpus.py
```

**Entradas:** corpus normalizado y el `normalizacion.json` de la misma carpeta. El hash registrado debe corresponder al TSV.

**Proceso:** aprende vocabularios independientes para las doce combinaciones:

```text
2 contenidos: título, texto
× 2 tamaños: unigramas, bigramas
× 3 representaciones: frecuencia, binaria, TF-IDF
= 12 espacios
```

Frecuencia cuenta apariciones; binaria registra presencia/ausencia; TF-IDF pondera frecuencia y rareza entre documentos, con IDF suavizado y norma L2. Los tokens se separan por espacios sin otra normalización. Los bigramas son parejas consecutivas de términos normalizados: pueden atravesar límites de oraciones o unir términos antes separados por palabras filtradas; nunca cruzan documentos.

**Salidas:** doce matrices dispersas `.npz`, doce vectorizadores `.joblib`, `ids_documentos.tsv` y `manifiesto.json`, dentro de `vectorizacion/`.

La consola presenta doce líneas de dimensiones. `N documentos × V características` significa N fragmentos y V términos o pares distintos; V variará con la nueva muestra. La fila i se identifica mediante `ids_documentos.tsv`; no debe ordenar ese archivo por separado.

En el manifiesto, `filas_sin_terminos` identifica documentos que no tienen características para esa configuración. Un título de una palabra no produce bigramas: puede tener una fila cero sin perderse del corpus. Si **todos** los títulos carecen de bigramas, el vocabulario correspondiente queda vacío y 07 puede detenerse. No invente títulos para evitarlo: esa muestra exige adaptar y documentar la configuración admitida por 07, 09 y 10 o ampliar la muestra con obras pertinentes.

Guarde matrices, modelos, IDs y manifiesto como un conjunto. Si cambia el corpus o 05, ejecute de nuevo 05 y 07 antes de buscar. No cargue archivos joblib de procedencia desconocida.

## 14. Script 09: realizar una consulta

```powershell
python scripts/09_recuperar_fragmentos.py --consulta "un personaje busca refugio durante una tormenta" --contenido texto --ngrama 1 --representacion tfidf --query-id PRUEBA01 --salida resultados/consultas/tormenta
```

**Entradas:** consulta libre, contenido, ngrama y representación; corpus normalizado y conjunto de vectorización compatibles.

| Argumento | Opciones o significado |
|---|---|
| `--consulta` | Texto en español que describe tema, situación, personaje, ambiente o motivo. |
| `--contenido` | `titulo` o `texto`. |
| `--ngrama` | `1` para unigramas o `2` para bigramas. |
| `--representacion` | `frecuencia`, `binaria` o `tfidf`. |
| `--query-id` | Identificador de esta consulta; no crea una anotación en el benchmark. |
| `--salida` | Carpeta de los resultados de esta ejecución. |
| `--vectorizacion` | Carpeta de artefactos, si se utiliza una distinta de la predeterminada. |

**Proceso:** comprueba compatibilidad, normaliza la consulta con las funciones de 05, aplica `transform` con el vectorizador ya ajustado y calcula similitud coseno. Ordena de mayor a menor y desempata por ID. No vuelve a aprender vocabulario ni IDF con la consulta.

**Salidas:** diez resultados en consola y, en la carpeta elegida, `rankings.tsv`, `consulta.json` e `informe.html`. El HTML muestra los textos originales completos. Use una carpeta distinta por consulta para conservar las ejecuciones; repetir la misma salida sobrescribe los archivos.

**Interpretación:** un score mayor expresa mayor parecido léxico en ese espacio, no probabilidad de relevancia ni calidad del pasaje. Dos pasajes pueden compartir palabras sin representar la misma situación, y uno pertinente puede usar sinónimos ausentes de la consulta.

Con pesos no negativos el coseno suele estar entre 0 y 1. Un cero significa que no hubo contribución compartida en esa representación. Cuando hay menos de diez coincidencias positivas, el programa completa el Top-10 con ceros y avisa; esos resultados no acreditan relevancia. Si la consulta queda vacía o sin vocabulario compartido, revise los avisos antes de interpretar el ranking.

Buscar por título compara con el título de la obra, repetido en sus fragmentos; no analiza el contenido del pasaje. Esto explica empates y la dificultad de usar títulos para consultas narrativas. Los bigramas requieren coincidencias más específicas que los unigramas.

El buscador entrega diez documentos distintos y necesita una muestra de al menos diez documentos para satisfacer esa operación. No use una prueba de tres fragmentos como si fuera el experimento completo.

## 15. Crear un benchmark para la nueva muestra

Puede utilizar el buscador sin benchmark, pero no evaluar su eficacia con las etiquetas del corpus anterior. Los scripts no generan automáticamente nuevos juicios de relevancia fiables.

### 15.1 Escribir queries.tsv

Cree `benchmark/queries.tsv` con estas columnas, separadas por tabulación:

```tsv
query_id	difficulty_level	query
Q01	1	Un personaje lee una carta.
Q02	1	Una discusión sobre dinero.
```

El ejemplo muestra el formato, **no un archivo completo aceptado por 10**. La implementación exige quince consultas únicas: cinco con nivel `1`, cinco con `2` y cinco con `3`. Puede definir el nivel 1 como situación explícita, el 2 como relación contextual y el 3 como motivo más implícito, documentando su criterio. El número de nivel no demuestra dificultad empírica.

Describa necesidades de información que tengan sentido para su muestra. Evite copiar párrafos del corpus como consulta o modificar consultas para favorecer una configuración después de ver resultados.

### 15.2 Juzgar los documentos y preparar qrels.tsv

Lea fragmentos completos y, cuando haga falta, el contexto de la obra. Use una rúbrica compartida:

- `2`: representa claramente la situación o motivo solicitado y sería una respuesta directa.
- `1`: relación parcial o secundaria, pero útil para esa necesidad.
- No pertinente o no juzgado: manténgalo identificado en sus notas; esta implementación de qrels no admite grado 0.

Prepare `benchmark/qrels.tsv`:

```tsv
query_id	document_id	relevance
Q01	F0007	2
Q01	F0042	1
```

Use los IDs de **su** corpus. El evaluador exige de 10 a 15 positivos por consulta y una mezcla de grados 1 y 2. No acepta pares duplicados ni IDs desconocidos. Son restricciones del ejercicio y del programa, no leyes de evaluación de recuperación. Si una consulta no tiene suficientes documentos realmente pertinentes, reformúlela antes de fijar el benchmark o adapte la metodología y el código; no fabrique relevancia para superar un control.

Este formato solo almacena positivos. Si existen más de quince relevantes, no puede representar una referencia exhaustiva con la restricción actual. Declare esa limitación y conserve un registro de juicios más completo, o adapte el evaluador de forma explícita si las condiciones del proyecto lo permiten.

### 15.3 Registrar la evidencia

Cree `benchmark/juicios_evidencia.tsv` para justificar cada decisión. Puede conservar las columnas de la entrega:

```text
query_id, document_id, relevance, justificacion, evidencia,
inicio, fin, ancla_literal, title, revisor, validacion_humana, alcance
```

En el archivo real use tabulaciones, no las comas explicativas de esa lista. Cite una frase o ancla localizable, indique quién revisó y si leyó el fragmento completo. Si usa offsets, defina su convención y el campo al que se refieren; pueden quedar vacíos si no se calcularon. No invente índices.

10 lee directamente `queries.tsv` y `qrels.tsv`; no interpreta ni genera `juicios_evidencia.tsv`. Usted debe mantenerlos consistentes. Es recomendable que otra persona revise discrepancias. Una propuesta de IA no debe registrarse como validación humana sin esa revisión.

### 15.4 Evitar conclusiones excesivas

Idealmente juzgue todos los fragmentos para cada consulta. Si revisa solo una parte, utilice al menos una unión de resultados de varias configuraciones y una muestra adicional fuera de esos rankings, y declare el alcance. Esto reduce sesgo, pero no demuestra exhaustividad.

Un documento ausente de qrels se computa como 0 en este ejercicio, aunque podría ser pertinente y no juzgado. Por eso las métricas describen la relación con la referencia anotada; con juicios incompletos no equivalen a precisión o recall reales sobre toda la colección.

Antes de evaluar, guarde una versión de consultas y juicios. No existe un script de congelación en la entrega mínima: el control de versiones o una copia fechada documentan esa decisión. Si cambia las etiquetas, ejecute de nuevo todas las configuraciones.

## 16. Script 10: evaluar las doce configuraciones

```powershell
python scripts/10_evaluar_benchmark.py --benchmark benchmark --salida resultados
```

**Entradas:** corpus activo, sus artefactos vectoriales y los dos TSV del benchmark nuevo.

**Proceso:** comprueba las restricciones anteriores, ejecuta las quince consultas en cada una de las doce configuraciones y compara el Top-10 con qrels. No prepara las consultas, no asigna relevancia y no corrige el corpus.

**Salidas esperadas si se completa:**

| Archivo | Contenido |
|---|---|
| `resultados/<configuracion>/rankings.tsv` | 150 posiciones: quince consultas por diez resultados. Columnas `query_id`, `document_id`, `rank`, `score`. |
| `resultados/<configuracion>/metricas.tsv` | Quince filas de métricas de esa configuración. |
| `metricas_por_consulta.tsv` | 180 filas: una por consulta y configuración. |
| `comparacion_configuraciones.tsv` | Doce filas con los promedios por configuración. |
| `metricas_por_nivel.tsv` | 36 filas: doce configuraciones por tres niveles. |
| `diagnostico_consultas.json` | Consulta normalizada, número de coincidencias positivas, avisos y documentos no juzgados del Top-10. |
| `resumen.json` | Totales, hashes de corpus/consultas/qrels, baseline y cinco mejores/peores casos relativos. |

En total son 180 rankings y 1800 posiciones. El script 10 **no genera un PDF ni un análisis cualitativo redactado**. Los archivos de informe y análisis de la muestra original fueron elaborados adicionalmente.

### Leer las métricas

| Métrica | Interpretación |
|---|---|
| P@10 | Positivos juzgados recuperados / 10. Si aparecen tres, vale 0.30. |
| R@10 | Positivos juzgados recuperados / positivos registrados para esa consulta. Con tres de doce, vale 0.25. |
| F1@10 | Media armónica de P@10 y R@10. Se calcula por consulta antes de promediar. |
| RR y MRR | RR es 1 / puesto del primer positivo, o 0 si no aparece en diez; MRR promedia RR. Si el primero está segundo, RR=0.5. |
| nDCG@10 | Evalúa orden y grados de relevancia frente al orden ideal de los juicios. Aquí usa ganancia `2^relevancia − 1`. |

En esas condiciones, valores más altos indican mejor ajuste a los juicios. No confunda score coseno con estas métricas: el primero ordena documentos y las segundas necesitan anotaciones externas.

La baseline fijada en el código es `texto_1_tfidf`. Los cinco mejores y cinco peores casos se eligen por su nDCG@10 en esa baseline, sin solapamiento y con desempate por ID. Son mejores y peores **relativos al experimento**, no evaluaciones universales de las consultas.

Revise siempre `diagnostico_consultas.json` junto con los promedios. Un ranking compuesto por ceros puede conseguir métricas no nulas por el desempate por ID. Eso no demuestra que el sistema haya identificado contenido pertinente.

El texto de estado de `resumen.json` conserva una referencia fija a juicios IA y validación humana pendiente del experimento original. Si su nueva referencia fue anotada por humanos, actualice esa descripción en el código o documente claramente la procedencia real en su informe; el programa no la infiere.

## 17. Elaborar el análisis y el informe nuevos

Después de ejecutar 10, no reutilice el PDF anterior cambiando únicamente nombres o cantidades. Redacte un informe sobre la nueva muestra con:

1. Obras, ediciones, autores, idioma y criterio de selección.
2. Parámetros de extracción/segmentación y decisiones de auditoría.
3. Problemas corregidos, excepciones y pendientes conocidos.
4. Política de normalización y doce representaciones utilizadas.
5. Consultas, criterios de relevancia, anotadores y alcance del juicio.
6. Tabla comparativa y resultados por nivel.
7. Cinco mejores y cinco peores casos de la baseline, explicados leyendo consulta, ranking, fragmentos y qrels.
8. Limitaciones: vocabulario, sinónimos, títulos repetidos, bigramas escasos, ceros, selección y juicios incompletos.

En cada caso de error distinga si falló el corpus, la normalización, la representación, la consulta o la referencia de relevancia. Un resultado discrepante no siempre implica un fallo del buscador: puede haber un positivo omitido en qrels.

Puede guardar el análisis como `resultados/analisis_errores.md` o JSON con un esquema que documente, y el informe final en `informes/`. Ninguno se genera automáticamente con los doce scripts conservados.

## 18. Qué repetir cuando algo cambia

| Cambio | Etapas que debe repetir o revisar |
|---|---|
| Nueva obra o nueva edición | Catálogo, extracción, segmentación, selección, auditoría, normalización, vectorización y benchmark. |
| Cambio de texto o límites de un fragmento | Auditoría de afectados y duplicados; 05, 07, consultas y evaluación; revisar juicios afectados. |
| Cambio solo de política/modelo de normalización | 05, 07, consultas y 10. El corpus literario puede permanecer igual. |
| Cambio de consultas o relevancia | Versionar benchmark y repetir 10 para las doce configuraciones. |
| Nueva consulta individual sin cambiar datos | Solo 09. |
| Cambio del nombre o ubicación de un TXT fuente | Revisar enlace con `book_id` y volver a comprobar correspondencia. |

Los controles internos no sustituyen esta gestión de versiones. Por ejemplo, modificar el corpus sin normalizar después de 05 no actualiza por sí mismo el normalizado. Mantenga los archivos activos sincronizados siguiendo el flujo.

## 19. Problemas frecuentes

| Síntoma | Qué comprobar |
|---|---|
| “No encontré EPUB” | Carpeta actual, extensión `.epub` y ubicación directa en `fuentes/epub/`. |
| Error al leer ZIP/XML/UTF-8 | EPUB válido y contenido compatible. El extractor no incluye recuperación universal de archivos dañados o codificaciones distintas. |
| Libros omitidos por catálogo | Nombre original, nombre TXT y revisión del catálogo; no cambie nombres entre etapas. |
| Pocos candidatos | Reporte de segmentación, capítulos, cantidad de texto, limpieza y longitud de las obras. |
| Menos de 300 seleccionados | Elegibles, márgenes, cuotas y cantidad de literatura. `--ajustar-a` no garantiza el total. |
| Origen ausente o ambiguo | `book_id` debe coincidir con un único nombre base TXT. |
| Faltan columnas o IDs duplicados | TSV con tabulaciones reales, encabezados exactos y lectura/escritura adecuada de celdas. |
| Modelo spaCy no encontrado | Dependencias instaladas en el Python que está ejecutando; no use un entorno diferente. |
| Hash o política incompatibles | Ejecute 05 y 07 de nuevo con los archivos y versiones activos; no edite el manifiesto para eludirlo. |
| Vocabulario vacío | Textos normalizados y posibilidad real de formar los ngramas; en títulos de una palabra no hay bigramas. |
| Diez resultados con cero | Avisos, vocabulario compartido y configuración. No interprete el orden por ID como relevancia. |
| Evaluación rechazada | Quince consultas, cinco por nivel; IDs conocidos; 10–15 positivos por consulta, ambos grados y sin duplicados. |
| Acentos extraños en consola | Abra los archivos UTF-8 para distinguir visualización de corrupción real; confirme contra el EPUB antes de reemplazar caracteres. |
| Ejecutó y no encuentra archivos | Revise la ruta que imprime el programa y el directorio actual. Algunas rutas se resuelven desde la raíz del script y otras desde PowerShell. |

Algunos programas de preparación imprimen un error y terminan sin devolver un código de fallo. Por eso debe leer la consola y confirmar que la salida corresponde a esta ejecución; la mera ausencia de una excepción no prueba que se haya construido la muestra.

Hay mensajes o comentarios heredados que mencionan nombres retirados, como `03_limpiar_segmentar.py` u `08_corregir_corpus`. Los ejecutables vigentes de esta entrega son los enumerados en esta guía. No existe un corrector automático general incluido.

## 20. Secuencia de consulta rápida

Esta lista sirve para localizar los comandos después de leer las explicaciones. **No se debe ejecutar como una cadena desatendida:** entre pasos hay revisión bibliográfica, auditoría, correcciones y anotación humana.

```powershell
# Desde la raíz nueva, con el entorno correcto y los EPUB preparados:
python scripts/00_generar_catalogo_libros.py
# Revisar y corregir catalogo_libros.csv.
python scripts/01_extraer_epub.py
# Cotejar los TXT con los EPUB.
python scripts/02_limpiar_segmentar.py --min-palabras 700 --max-palabras 1300 --objetivo 1000
# Revisar reporte_segmentacion.csv y márgenes de selección.
python scripts/03_seleccionar_fragmentos.py --ajustar-a 300
python scripts/04_auditar_corpus.py
python scripts/04b_auditar_coherencia.py --contexto 1200
# Revisar, corregir, repetir auditorías y cerrar una versión del corpus.
python scripts/05_normalizar_corpus.py
python scripts/07_vectorizar_corpus.py
python scripts/09_recuperar_fragmentos.py --consulta "una disputa entre familiares" --contenido texto --ngrama 1 --representacion tfidf --salida resultados/consultas/disputa
# Crear y revisar queries.tsv, qrels.tsv y sus evidencias para este corpus.
python scripts/10_evaluar_benchmark.py --benchmark benchmark --salida resultados
# Interpretar resultados y redactar un informe nuevo.
```

Para compartir la nueva muestra, incluya código, dependencias, catálogo corregido, corpus y fuentes de cotejo que pueda distribuir, auditorías de esa versión, artefactos vectoriales, benchmark documentado, resultados e informe propio. Escriba un README que identifique la muestra, las versiones y las limitaciones. Los datos incluidos deben permitir a otra persona distinguir qué fue generado, qué fue revisado y qué permanece pendiente.
