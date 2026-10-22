"""
config_seleccion.py -- parametros de la Etapa B (04_seleccionar_fragmentos.py).

Todo lo que probablemente quieras ajustar esta aqui. Los argumentos de linea
de comandos del script tienen prioridad sobre estos valores.
"""
import re
import unicodedata

# ---------------------------------------------------------------------------
# 1) ELEGIBILIDAD de los candidatos de la Etapa A
#    (la Etapa A genera 700-1300; aqui se permite un poco mas de margen)
# ---------------------------------------------------------------------------
MIN_ACEPTABLE = 500
MAX_ACEPTABLE = 1300
PREFERIDO_MIN_PALABRAS = 700    # fragmentos por debajo de esto pierden puntos
PENALIZACION_CORTO = 0.10       # puntos que pierde un fragmento < PREFERIDO_MIN_PALABRAS

# ---------------------------------------------------------------------------
# 2) CUOTAS: cuantos fragmentos se toman de cada obra
#    - cuento: FRAGMENTOS_CUENTO (2 = presentacion/conflicto + climax/desenlace)
#    - novela y novela_corta: un fragmento por cada PALABRAS_POR_FRAGMENTO
#      palabras, entre MIN_NOVELA y MAX_NOVELA, y sin pasar de MAX_COBERTURA
#      (fraccion de la obra que se permite cubrir; protege a las novelas cortas)
# ---------------------------------------------------------------------------
FRAGMENTOS_CUENTO = 2
PALABRAS_POR_FRAGMENTO = 15000
MIN_NOVELA = 8
MAX_NOVELA = 20
MAX_COBERTURA = 0.35
UMBRAL_NOVELA = 20000           # si el catalogo no dice 'tipo': menos palabras = cuento

# ---------------------------------------------------------------------------
# 3) ZONAS (posicion relativa 0.0-1.0). Dentro de cada zona se elige el
#    fragmento de mayor IMPORTANCIA; la zona garantiza la cobertura del arco.
#      novelas: k zonas del mismo ancho
#      cuentos de 2 fragmentos: (desde, hasta, punto_objetivo)
# ---------------------------------------------------------------------------
ZONAS_CUENTO = [
    (0.00, 0.30, 0.05),   # presentacion del personaje y del conflicto
    (0.70, 1.01, 0.85),   # climax y desenlace
]
MAX_POR_CAPITULO = 2      # tope de fragmentos de un mismo capitulo (se relaja si no hay alternativa)

# ---------------------------------------------------------------------------
# 4) IMPORTANCIA = consultas + centralidad + cercania al punto objetivo de la zona
# ---------------------------------------------------------------------------
PESOS = {
    "consultas": 0.5,       # cercania a las consultas de "momentos importantes"
    "centralidad": 0.3,     # cercania al vocabulario central de la obra
    "posicion": 0.2,        # cercania al punto objetivo de su zona
}

# ---------------------------------------------------------------------------
# 5) CONSULTAS de "momento importante" (genericas para narrativa de cualquier
#    genero). Calce lexico por raices de 5 letras.
#    IMPORTANTE: son consultas de SELECCION. No copies aqui las consultas del
#    benchmark (queries.tsv); si se parecen, los resultados de evaluacion salen
#    inflados porque el corpus se eligio para responderlas.
# ---------------------------------------------------------------------------
CONSULTAS_IMPORTANTES = {
    "conflicto": "pelea lucha combate batalla duelo enfrentamiento disputa discusion ataque enemigo rival amenaza",
    "muerte_perdida": "morir muerte muerto cadaver matar asesinato funeral luto perdida agonia tumba dolor",
    "amor_pasion": "amor amar amante pasion deseo beso celos enamorado esposa marido boda adulterio abandono",
    "traicion_engano": "traicion traidor engaño mentira mentir venganza culpa crimen delito robo acusacion juicio",
    "revelacion_secreto": "revelar revelacion secreto verdad confesion descubrir descubrimiento identidad misterio sorpresa",
    "viaje_partida": "partir partida viaje viajar camino travesia huir huida escapar regreso llegada exilio",
    "peligro_catastrofe": "peligro tormenta naufragio incendio epidemia hambre miseria ruina catastrofe desastre fuga",
    "sobrenatural": "fantasma espectro monstruo demonio sueño pesadilla locura maldicion hechizo aparicion horror",
    "decision_dilema": "decidir decision dilema conciencia juramento promesa sacrificio renuncia conversion arrepentimiento",
    "resolucion": "victoria triunfo libre salvado salvacion reconciliacion reencuentro final desenlace fortuna herencia",
}

# ---------------------------------------------------------------------------
# Tokenizacion simple (sin spaCy/NLTK): minusculas, sin acentos, stopwords
# fuera y recorte a una "raiz" de 5 letras.
# ---------------------------------------------------------------------------
RAIZ = 5

STOPWORDS = set("""
a al algo algun alguna algunas alguno algunos ante antes aquel aquella aquellas aquellos aqui asi aun aunque
bien cada casi como con contra cual cuales cuando de del desde donde dos durante e el ella ellas ello ellos en
entre era eran eras eres es esa esas ese eso esos esta estaba estaban estado estan estar este esto estos fue
fueron ha haber habia habian hace hacer hacia han hasta hay la las le les lo los mas me mi mis mucho muy ni no
nos nosotros nuestro o os otra otras otro otros para pero poco por porque que quien quienes se sea segun ser si
sido sin sobre son su sus tal tambien tan tanto te tenia ti todo todos tu tus un una unas uno unos usted ya yo
""".split())


def quitar_acentos(texto):
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in texto if not unicodedata.combining(c))


def tokenizar(texto):
    texto = quitar_acentos(texto.lower()).replace("ñ", "n")
    tokens = re.findall(r"[a-z]{2,}", texto)
    return [t[:RAIZ] for t in tokens if t not in STOPWORDS]
