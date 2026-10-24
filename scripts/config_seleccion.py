import re
import unicodedata

MIN_ACEPTABLE = 500
MAX_ACEPTABLE = 1300
PREFERIDO_MIN_PALABRAS = 700    # fragmentos por debajo de esto pierden puntos
PENALIZACION_CORTO = 0.10       # puntos que pierde un fragmento < PREFERIDO_MIN_PALABRAS

FRAGMENTOS_CUENTO = 2
PALABRAS_POR_FRAGMENTO = 15000
MIN_NOVELA = 8
MAX_NOVELA = 20
MAX_COBERTURA = 0.35
UMBRAL_NOVELA = 20000           

ZONAS_CUENTO = [
    (0.00, 0.30, 0.05),   # presentacion del personaje y del conflicto
    (0.70, 1.01, 0.85),   # climax y desenlace
]
MAX_POR_CAPITULO = 2      

PESOS = {
    "consultas": 0.5,      
    "centralidad": 0.3,    
    "posicion": 0.2,       
}

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
