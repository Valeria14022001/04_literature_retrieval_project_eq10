"""Prioriza indicios de cortes narrativos; no evalúa calidad ni modifica el corpus.

python scripts/04b_auditar_coherencia.py
Solo biblioteca estándar de Python 3.10+. Ver --help.
"""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(text):
    """Vista auxiliar con mapa a caracteres originales; jamás sustituye la fuente.

    Unifica espacios, rayas y guiones de fin de línea. Conserva letras, acentos,
    caja y signos restantes. Se usa para localizar, no para exhibir el texto.
    """
    skip = set()
    for match in re.finditer(r'(?<=[^\W\d_])-\s*\n\s*(?=[^\W\d_])', text):
        skip.update(range(match.start(), match.end()))
    chars, offsets = [], []
    for i, char in enumerate(text):
        if i in skip or char.isspace():
            continue
        chars.append('—' if char == '–' else char)
        offsets.append(i)
    return ''.join(chars), offsets


def occurrences(text, pattern):
    result, start = [], 0
    while pattern:
        pos = text.find(pattern, start)
        if pos < 0:
            break
        result.append(pos)
        start = pos+1
    return result


def grams(text, k=12):
    return {text[i:i+k] for i in range(max(0, len(text)-k+1))}


def locate(text, source, canonical_source=None):
    if not text.strip():
        return dict(estado='Texto vacío')
    exact = occurrences(source, text)
    if len(exact) == 1:
        return dict(estado='Literal', inicio=exact[0], fin=exact[0]+len(text))
    if len(exact) > 1:
        return dict(estado='Ambigua: varias coincidencias literales')
    canon, mapping = canonical_source or canonical(source)
    target, _ = canonical(text)
    if len(target) < 100:
        return dict(estado='No localizado: demasiado corto para anclas')
    matches = occurrences(canon, target)
    if len(matches) == 1:
        a = matches[0]
        return dict(estado='Vista auxiliar: espacios/guiones/rayas',
                    inicio=mapping[a], fin=mapping[a+len(target)-1]+1)
    if len(matches) > 1:
        return dict(estado='Ambigua: varias coincidencias auxiliares')
    starts = occurrences(canon, target[:100])
    ends = occurrences(canon, target[-100:])
    candidates = [(a,b+100) for a in starts for b in ends
                  if .8*len(target) <= b+100-a <= 1.25*len(target)]
    if len(candidates) != 1:
        return dict(estado='No localizado o anclas ambiguas')
    a,b = candidates[0]
    ref = grams(target)
    overlap = len(ref & grams(canon[a:b]))/max(1,len(ref))
    if overlap < .95:
        return dict(estado='Alineación rechazada', cobertura_ngramas=round(overlap,4))
    return dict(estado='Aproximada: anclas únicas; revisar diferencias internas',
                inicio=mapping[a], fin=mapping[b-1]+1, cobertura_ngramas=round(overlap,4))


def edge_units(text):
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    if len(paragraphs) > 1:
        return paragraphs[0], paragraphs[-1], 'Párrafos conservados en el fragmento'
    return text[:900], text[-900:], 'Ventanas de extremos; separadores de párrafo ausentes'


def detect(text, first=None, last=None):
    alerts = []
    def add(code, priority, evidence, reason):
        alerts.append(dict(codigo=code, prioridad=priority, evidencia=evidence, motivo=reason))
    first, last = (first, last) if first is not None else edge_units(text)[:2]
    start = text.strip().lstrip('«“"\'([{—–- ')
    end = text.strip().rstrip('»”"\')]} ')
    dependent = re.match(r'(?i)^(por eso|por ello|por lo tanto|sin embargo|no obstante|aquello|aquella situación|dicha situación|de ese modo|así pues|entonces)\b', start)
    if dependent:
        add('inicio_dependiente', 'baja', dependent.group(), 'Referencia a antecedentes; puede ser legítima.')
    if start and start[0].islower():
        add('inicio_minuscula', 'media', text[:160], 'Posible inicio dentro de una oración; revisar estilo del autor.')
    if text.strip().startswith((',', ';', ':', ')', ']', '…', '...')):
        add('inicio_signo_continuacion', 'media', text[:160], 'El signo inicial puede depender de texto anterior.')
    if end and not re.search(r'[.!?…]$', end):
        add('final_sin_cierre', 'media', text[-180:], 'No hay signo de cierre; puede ser título, verso o corte.')
    connector = re.search(r'(?i)\b(porque|aunque|cuando|ya que|puesto que|sin embargo|por lo tanto|pero|mientras|si)\s*[,;:—–-]*$', end)
    if connector:
        add('final_conector', 'alta', text[-180:], 'Conector final que parece anticipar una continuación.')
    if re.search(r'[:—–-]$|\.{3}$|…$', end):
        add('final_suspension', 'baja', text[-180:], 'Final en suspensión; puede ser deliberado.')
    if re.match(r'^\s*[—–-]', first or ''):
        add('dialogo_inicial', 'baja', (first or '')[:200], 'Comienza con intervención de diálogo; posible antecedente externo.')
    if re.search(r'\b(?:dijo|preguntó|respondió|replicó|exclamó)\s*:?\s*$', end, re.I):
        add('dialogo_anunciado_sin_turno', 'media', text[-180:], 'Parece anunciar una intervención no incluida.')
    if re.search(r'[—–]\s*$', last or ''):
        add('dialogo_final_abierto', 'media', (last or '')[-180:], 'Raya final sin continuación visible; comprobar diálogo.')
    for opening, closing in [('«','»'), ('“','”'), ('(',')'), ('[',']')]:
        balance = text.count(opening)-text.count(closing)
        if balance:
            add('delimitador_desbalanceado', 'media', f'{opening}{closing}: diferencia {balance}',
                'Posible cita o inciso cortado; algunas convenciones literarias usan varias aperturas.')
    chapter = re.search(r'(?im)(?:^|\n)\s*(?:cap[íi]tulo\s+(?:\d+|[IVXLCDM]+)\b|parte\s+[IVXLCDM]+\b)', text)
    if chapter:
        add('encabezado_visible', 'media', chapter.group().strip(), 'Posible cambio de capítulo dentro del pasaje.')
    elif re.search(r'(?i)\bcap[íi]tulo\s+(?:\d+|[IVXLCDM]+)\b', text):
        add('mencion_capitulo', 'baja', re.search(r'(?i).{0,35}\bcap[íi]tulo\s+(?:\d+|[IVXLCDM]+)\b.{0,50}', text).group(), 'Puede ser encabezado aplanado o una mención narrativa.')
    bad = Counter(c for c in text if c=='\ufffd' or (unicodedata.category(c) in ('Cc','Cs') and c not in '\r\n\t'))
    if bad:
        add('caracteres_anomalos', 'alta', str({f'U+{ord(c):04X}':n for c,n in bad.items()}), 'Caracteres de sustitución o controles inesperados.')
    mojibake = re.search(r'Ã.|Â.|â€|ï¿½', text)
    if mojibake:
        add('posible_mojibake', 'media', mojibake.group(), 'Indicio heurístico de error de codificación.')
    joined = re.search(r'[.!?][A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]{2,}', text)
    if joined:
        add('posible_separador_perdido', 'media', text[max(0,joined.start()-45):joined.end()+65], 'Signo seguido de palabra sin espacio; admite abreviaturas y usos legítimos.')
    return alerts


def run(args):
    inputs = sorted(args.origen.rglob('*.txt'))
    tracked = [args.corpus] + inputs
    if args.candidatos.exists():
        tracked.append(args.candidatos)
    hashes = {str(p.resolve()):digest(p) for p in tracked}
    with args.corpus.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f, delimiter='\t')
        if not {'fragment_id','book_id','text'} <= set(reader.fieldnames or []):
            raise ValueError('Faltan columnas fragment_id, book_id o text')
        rows = list(reader)
    if any(None in r or any(v is None for v in r.values()) for r in rows):
        raise ValueError('TSV con filas mal formadas')
    candidates = defaultdict(list)
    if args.candidatos.exists():
        with args.candidatos.open(encoding='utf-8-sig', newline='') as f:
            for r in csv.DictReader(f, delimiter='\t'):
                candidates[r.get('book_id',''),r.get('candidato_id','')].append(r)
    sources = defaultdict(list)
    for p in inputs:
        sources[p.stem].append(p)
    cache, records = {}, []
    for number,row in enumerate(rows,1):
        text = row['text']
        first,last,units = edge_units(text)
        location = dict(estado='Fuente ausente o ambigua')
        source, previous, following, passage = '', '', '', ''
        paths = sources[row['book_id']]
        if len(paths)==1:
            p = paths[0]
            if p not in cache:
                with p.open(encoding='utf-8-sig', newline='') as f:
                    raw = f.read()
                cache[p] = raw, canonical(raw)
            source, canon = cache[p]
            location = locate(text, source, canon)
            location['archivo'] = str(p.resolve())
            if 'inicio' in location:
                a,b = location['inicio'], location['fin']
                previous,following = source[max(0,a-args.contexto):a],source[b:b+args.contexto]
                passage = source[a:b]
                if '\n' not in text:
                    source_first,source_last,source_units = edge_units(passage)
                    if source_units.startswith('Párrafos'):
                        first,last,units = source_first,source_last,'Párrafos de la fuente; pueden contener residuos eliminados del corpus'
                    else:
                        units += '; fuente sin límites de párrafo inequívocos'
        alerts = detect(text, first,last)
        if not text.strip():
            alerts.append(dict(codigo='texto_vacio',prioridad='alta',evidencia='',motivo='No hay contenido que inspeccionar.'))
        metadata = candidates[row['book_id'],row.get('candidato_id','')]
        if len(metadata)==1 and metadata[0].get('text')==text:
            try:
                if int(metadata[0].get('capitulos_unidos','0'))>1:
                    alerts.append(dict(codigo='capitulos_unidos',prioridad='media',evidencia=metadata[0].get('capitulo',''),motivo='El candidato declara varios capítulos; revisar transición, no implica error.'))
            except ValueError:
                pass
        elif re.search(r'\s\+\s',row.get('chapter_position','')):
            alerts.append(dict(codigo='varios_capitulos_metadato',prioridad='baja',evidencia=row['chapter_position'],motivo='Etiqueta compuesta; candidatos ausentes o sin correspondencia exacta.'))
        if 'inicio' in location:
            before = previous.rstrip()
            after = following.lstrip()
            # Solo se sugiere corte interno si ambos lados se continúan en la
            # misma línea y no hay signo de cierre inmediato.
            if before and previous and not re.search(r'\n\s*$', previous) and before[-1] not in '.!?…:»”"' and text.lstrip()[:1].islower():
                alerts.append(dict(codigo='inicio_dentro_oracion_fuente',prioridad='alta',evidencia=previous[-140:]+' | '+text[:140],motivo='La fuente parece continuar una oración a través del corte.'))
            stripped_end = text.rstrip().rstrip('»”"\')]}')
            if after and following and not re.match(r'^\s*\n', following) and stripped_end and stripped_end[-1] not in '.!?…' and (after[:1].islower() or after.startswith((',', ';'))):
                alerts.append(dict(codigo='final_dentro_oracion_fuente',prioridad='alta',evidencia=text[-140:]+' | '+following[:140],motivo='La oración parece continuar inmediatamente en la fuente.'))
        priority = 'alta' if any(a['prioridad']=='alta' for a in alerts) else 'media' if any(a['prioridad']=='media' for a in alerts) else 'baja' if alerts else 'sin_indicios'
        records.append(dict(fila=number,fragment_id=row['fragment_id'],book_id=row['book_id'],
            title=row.get('title',''),prioridad=priority,alertas=alerts,texto=text,
            primer_parrafo_o_ventana=first,ultimo_parrafo_o_ventana=last,unidades=units,
            localizacion=location,contexto_anterior=previous,pasaje_fuente=passage,contexto_posterior=following))
    if any(digest(Path(p))!=value for p,value in hashes.items()):
        raise RuntimeError('Cambió una entrada durante la auditoría; repetir ejecución')
    args.salida.mkdir(parents=True,exist_ok=True)
    summary = dict(fecha_utc=datetime.now(timezone.utc).isoformat(),fragmentos=len(records),
        prioridades=dict(Counter(r['prioridad'] for r in records)),
        indicadores=dict(Counter(a['codigo'] for r in records for a in r['alertas'])),
        localizacion=dict(Counter(r['localizacion']['estado'] for r in records)),
        huellas_entradas=hashes,parametros={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()})
    (args.salida/'resumen.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    (args.salida/'fragmentos.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    with (args.salida/'revision.csv').open('w',encoding='utf-8-sig',newline='') as f:
        columns = ['fila','fragment_id','book_id','prioridad','indicadores','localizacion','decision_humana','observaciones']
        writer=csv.DictWriter(f,fieldnames=columns)
        writer.writeheader()
        for r in records:
            writer.writerow({k:r[k] for k in columns[:4]} | dict(indicadores='; '.join(a['codigo'] for a in r['alertas']),localizacion=r['localizacion']['estado'],decision_humana='',observaciones=''))
    esc = lambda value:html.escape(str(value))
    rank={'alta':0,'media':1,'baja':2,'sin_indicios':3}
    cards=[]
    for r in sorted(records,key=lambda r:(rank[r['prioridad']],r['fila'])):
        findings=''.join('<li><b>'+esc(a['codigo'])+' ('+a['prioridad']+')</b>: '+esc(a['motivo'])+'<blockquote>'+esc(a['evidencia'])+'</blockquote></li>' for a in r['alertas'])
        cards.append('<details class="card" data-priority="'+r['prioridad']+'"><summary>'+esc(r['fragment_id']+' · '+r['title']+' · '+r['prioridad'])+f' · {len(r["alertas"])} indicios</summary><ul>'+findings+'</ul><p>'+esc(r['unidades'])+'</p><h3>Primer párrafo o ventana</h3><pre>'+esc(r['primer_parrafo_o_ventana'])+'</pre><h3>Último párrafo o ventana</h3><pre>'+esc(r['ultimo_parrafo_o_ventana'])+'</pre><h3>Localización</h3><pre>'+esc(json.dumps(r['localizacion'],ensure_ascii=False,indent=2))+'</pre><h3>Antes, en la fuente</h3><pre>'+esc(r['contexto_anterior'])+'</pre><h3>Fragmento del corpus (íntegro)</h3><pre>'+esc(r['texto'])+'</pre><h3>Después, en la fuente</h3><pre>'+esc(r['contexto_posterior'])+'</pre><details><summary>Pasaje completo de la fuente para comparar diferencias internas</summary><pre>'+esc(r['pasaje_fuente'])+'</pre></details></details>')
    page='''<!doctype html><html lang="es"><meta charset="utf-8"><title>Indicios de coherencia narrativa</title><style>body{font:16px system-ui;max-width:1100px;margin:30px auto;padding:0 20px;color:#183047}.card{border:1px solid #b9cbd6;margin:12px 0;padding:14px;border-radius:8px}summary{cursor:pointer;font-weight:600}pre{white-space:pre-wrap;font:15px/1.6 Georgia,serif;background:#f3f6f8;padding:15px}blockquote{border-left:3px solid #adbac4;padding-left:12px}select,input{padding:9px;margin:8px}</style><h1>Indicios de coherencia narrativa</h1><p>Este detector prioriza revisión humana. Las alertas no demuestran errores; ausencia de alertas no certifica coherencia, autonomía ni continuidad de personajes. Un diálogo inicial y un final abierto pueden ser literariamente válidos. El TSV puede haber perdido todos sus separadores de párrafo: no se inventan. La alineación aproximada admite diferencias internas y necesita revisión; no certifica fidelidad. Los contextos son ventanas de caracteres originales, no necesariamente párrafos completos. Índices desde cero, fin exclusivo.</p><label>Prioridad <select id="priority"><option value="sospechosos">Todos los candidatos sospechosos</option><option value="alta">Alta</option><option value="media">Media</option><option value="baja">Baja</option><option value="sin_indicios">Sin indicios</option><option value="todos">Todos</option></select></label><input id="search" placeholder="Buscar identificador, obra o texto"><p id="count"></p>'''+''.join(cards)+'''<script>const cards=[...document.querySelectorAll('.card')];function filter(){let n=0;for(const c of cards){const p=document.querySelector('#priority').value;const q=document.querySelector('#search').value.toLocaleLowerCase();const show=(p==='todos'||p===c.dataset.priority||(p==='sospechosos'&&c.dataset.priority!=='sin_indicios'))&&c.textContent.toLocaleLowerCase().includes(q);c.hidden=!show;if(show)n++;}document.querySelector('#count').textContent=n+' fragmentos visibles';}document.querySelector('#priority').onchange=filter;document.querySelector('#search').oninput=filter;filter();</script></html>'''
    (args.salida/'informe.html').write_text(page,encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='huellas_entradas'},ensure_ascii=False,indent=2))
    print('Informe:',args.salida/'informe.html')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus',type=Path,default=ROOT/'datos/literature_raw_corpus.tsv')
    parser.add_argument('--origen',type=Path,default=ROOT/'textos_extraidos')
    parser.add_argument('--candidatos',type=Path,default=ROOT/'datos/candidatos/candidatos.tsv')
    parser.add_argument('--salida',type=Path,default=ROOT/'datos/auditoria_narrativa')
    parser.add_argument('--contexto',type=int,default=1200,help='Caracteres anteriores y posteriores de la fuente')
    args=parser.parse_args()
    if args.contexto<1:
        parser.error('--contexto debe ser positivo')
    out=args.salida.resolve()
    protected=[args.corpus.resolve(),args.candidatos.resolve(),*args.origen.rglob('*.txt')]
    if any(p.resolve().parent==out for p in protected):
        parser.error('Usa una carpeta de salida separada de las entradas')
    run(args)


if __name__=='__main__':
    main()
