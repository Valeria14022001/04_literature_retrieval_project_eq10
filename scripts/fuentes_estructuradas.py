from pathlib import PurePosixPath
from zipfile import ZipFile
from urllib.parse import unquote
import hashlib
import re
import unicodedata
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup


def slug(s):
    s=unicodedata.normalize('NFKD',s.lower())
    s=''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'\s+','_',re.sub(r'[^\w\s-]','',s))[:120]


def spine(z):
    root=ET.fromstring(z.read('META-INF/container.xml'))
    opf=next(e.attrib['full-path'] for e in root.iter() if e.tag.endswith('rootfile'))
    root=ET.fromstring(z.read(opf)); manifest={}
    import posixpath
    for e in root.iter():
        if e.tag.endswith('}item'):
            href=unquote(e.attrib.get('href','')).split('#')[0]
            manifest[e.attrib['id']]=posixpath.normpath(str(PurePosixPath(opf).parent/href))
    return [manifest[e.attrib['idref']] for e in root.iter()
            if e.tag.endswith('}itemref') and e.attrib.get('idref') in manifest]


def extract_book(path):
    blocks=[]; removed=[]; book=slug(path.stem)
    with ZipFile(path) as z:
        for member in spine(z):
            if not member.lower().endswith(('.html','.htm','.xhtml','.xml')): continue
            low=member.lower()
            if any(x in PurePosixPath(low).name for x in ('cover','titlepage','elejandria_title','ncl_indice')) or PurePosixPath(low).stem in ('title','titulo','nav','toc'):
                removed.append(dict(member=member,reason='Portada, título o navegación del EPUB')); continue
            if book.startswith('los_pazos_de_ulloa') and 'apuntes_autobiograficos' in low:
                removed.append(dict(member=member,reason='Preliminar autobiográfico separado de la novela; preservado en EPUB original')); continue
            data=z.read(member)
            raw=data.decode('utf-8-sig',errors='strict')
            soup=BeautifulSoup(raw,'html.parser')
            for t in soup(['script','style','head','nav','metadata']): t.decompose()
            for t in list(soup.find_all(True)):
                if t.parent is None: continue
                roles=t.get('epub:type','').split()
                ident=t.get('id','')
                if 'footnote' in roles or 'noteref' in roles or ident.startswith(('conv-idiomas','dic-local-es-act','cite_ref')):
                    removed.append(dict(member=member,text=t.get_text(' ',strip=True),
                        reason='Nota editorial, llamada de nota o widget de conversión de idiomas identificado por atributos EPUB/HTML'))
                    t.decompose()
            body=soup.body or soup
            tags=body.find_all(['p','h1','h2','h3','h4','h5','h6','li','pre'])
            tags=[t for t in tags if not t.find_parent(['p','h1','h2','h3','h4','h5','h6','li','pre'])]
            if not tags:
                tags=[body]
            for index,tag in enumerate(tags):
                # HTML colapsa los saltos de línea del código, pero br es un corte real.
                for br in tag.find_all('br'): br.replace_with('\uE000')
                text=tag.get_text('',strip=False).replace('\xa0',' ')
                # Un guion seguido de salto físico dentro de un nodo de texto es
                # huella de división de línea; no se tocan guiones sin ese salto.
                text=re.sub(r'(?<=[^\W\d_])-\s*\r?\n\s*(?=[^\W\d_])','',text)
                text=re.sub(r'\s+',' ',text).strip().replace('\uE000','\n')
                text=re.sub(r' *\n *','\n',text).strip()
                if not text: continue
                reason=None
                if re.search(r'libro descargado en|www\.elejandria\.com|esperamos que lo disfrut',text,re.I): reason='Aviso de descarga'
                if book.startswith('el_lobo_estepario') and text in ('Hermann Hesse','El lobo estepario'):
                    reason='Encabezado repetido de autor o título'
                if book.startswith('el_lobo_estepario') and re.fullmatch(r'\d{1,3}',text) and index>=len(tags)-4:
                    reason='Paginación final junto al encabezado de la página siguiente'
                if reason:
                    removed.append(dict(member=member,block=index,text=text,reason=reason)); continue
                kind='heading' if tag.name.startswith('h') else 'paragraph'
                m=re.match(r'^h3\s+style=[\s\S]*?>\s*',text)
                if m:
                    removed.append(dict(member=member,block=index,text=m.group(),reason='Etiqueta h3 escapada y fragmentada en el EPUB'))
                    text=text[m.end():]; kind='heading'
                if book.startswith('el_sabueso_de_los_baskerville'):
                    # Fecha moderna repetida como residuo de exportación en una
                    # novela y edición anteriores; no es fecha del diario de Watson.
                    for m in re.finditer(r'19/12/2015',text):
                        removed.append(dict(member=member,block=index,text=m.group(),reason='Fecha repetida de exportación, no narrativa'))
                    text=re.sub(r' *19/12/2015 *',' ',text).strip()
                # Los marcadores internos de página vacíos no producen texto; no
                # se elimina ningún numeral narrativo por regla general.
                blocks.append(dict(text=text,kind=kind,origins=[dict(member=member,block=index,tag=tag.name)]))
    # En archivos provenientes de PDF una oración puede continuar en el archivo
    # siguiente. Unir solo con evidencia de palabra inicial minúscula y sin cierre.
    joined=[]
    for b in blocks:
        if joined and b['kind']=='paragraph' and joined[-1]['kind']=='paragraph' and re.search(r'[^\W\d_]-$',joined[-1]['text']) and re.match(r'^[a-záéíóúüñ]',b['text']):
            removed.append(dict(member=b['origins'][0]['member'],text=joined[-1]['text'][-50:]+' / '+b['text'][:50],reason='Reunión de palabra partida por guion entre bloques consecutivos'))
            joined[-1]['text']=joined[-1]['text'][:-1]+b['text']; joined[-1]['origins']+=b['origins']; continue
        if joined and b['kind']=='paragraph' and joined[-1]['kind']=='paragraph' and b['origins'][0]['member']!=joined[-1]['origins'][-1]['member']:
            previous=joined[-1]['text']
            if previous and not re.search(r'[.!?…:»”"]$',previous) and re.match(r'^[a-záéíóúüñ]',b['text']):
                joined[-1]['text']+=' '+b['text']; joined[-1]['origins']+=b['origins']; continue
        joined.append(b)
    offset=0
    for b in joined:
        b['start']=offset; b['end']=offset+len(b['text']); offset=b['end']+2
    return dict(book_id=book,epub=str(path.resolve()),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                blocks=joined,removed=removed,text='\n\n'.join(b['text'] for b in joined))


def safe_sentence_spans(text):
    start=0
    for m in re.finditer(r'(?<=[.!?…])\s+(?=[—–\-«“"¿¡A-ZÁÉÍÓÚÜÑ])',text):
        prefix=text[:m.start()]
        token=re.search(r'([^\s]+)$',prefix)
        last=token.group(1) if token else ''
        if re.fullmatch(r'[A-ZÁÉÍÓÚÜÑ]\.',last) or last.lower() in ('sr.','sra.','srta.','dr.','dra.','d.','ud.','vd.','vds.','uds.','etc.','mr.','mrs.','st.'):
            continue
        yield start,m.start()
        start=m.end()
    if start<len(text): yield start,len(text)


def cutting_units(book):
    result=[]
    for i,b in enumerate(book['blocks']):
        spans=list(safe_sentence_spans(b['text'])) if len(b['text'].split())>350 and b['kind']=='paragraph' else [(0,len(b['text']))]
        for part,(a,z) in enumerate(spans):
            unit=dict(b); unit.update(text=b['text'][a:z],start=b['start']+a,end=b['start']+z,paragraph=i,part=part)
            result.append(unit)
    return result


def auxiliary(text):
    chars=[]; offsets=[]
    for i,c in enumerate(text):
        if c.isalnum(): chars.append(c); offsets.append(i)
    return ''.join(chars),offsets


def align_fragment(text,book):
    target,_=auxiliary(text)
    source,mapping=book['_aux']
    starts=[]; ends=[]
    for displacement in range(0,min(700,len(target)//3),30):
        a=target[displacement:displacement+90]
        k=source.find(a)
        if k>=0 and source.find(a,k+1)<0: starts.append((k,displacement)); break
    for displacement in range(0,min(700,len(target)//3),30):
        a=target[len(target)-displacement-90:len(target)-displacement]
        k=source.find(a)
        if k>=0 and source.find(a,k+1)<0: ends.append((k+90,displacement)); break
    if not starts or not ends: return None
    a,da=starts[0]; b,db=ends[0]
    if not .65*len(target)<=b-a<=1.6*len(target): return None
    ca,cb=mapping[a],mapping[b-1]+1
    indexes=[i for i,x in enumerate(book['units']) if x['end']>ca and x['start']<cb]
    return dict(first=indexes[0],last=indexes[-1],anchor_start=ca,anchor_end=cb,
                omitted_prefix=da,omitted_suffix=db,method='Anclas únicas auxiliares; extremos expandidos a bloques EPUB')
