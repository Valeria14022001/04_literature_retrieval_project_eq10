"""Ejecuta las 12 configuraciones y evalúa contra los qrels de desarrollo."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'benchmark'
BASELINE='texto_1_tfidf'  # elegida antes de ejecutar los rankings

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f,delimiter='\t'))

def write(path,rows,fields):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter='\t'); w.writeheader(); w.writerows(rows)

def metricas(docs,rel,k=10):
    if len(docs)!=k or len(set(docs))!=k:
        raise ValueError('El ranking debe tener diez documentos distintos.')
    labels=[rel.get(d,0) for d in docs]
    total=sum(v>0 for v in rel.values())
    if not total: raise ValueError('Consulta sin relevantes en qrels.')
    hits=sum(v>0 for v in labels)
    p,r=hits/k,hits/total
    rr=next((1/i for i,v in enumerate(labels,1) if v>0),0.)
    gain=lambda values: sum((2**v-1)/math.log2(i+1) for i,v in enumerate(values,1))
    ideal=gain(sorted(rel.values(),reverse=True)[:k])
    return {'P@10':p,'R@10':r,'F1@10':2*p*r/(p+r) if p+r else 0.,'RR':rr,'nDCG@10':gain(labels)/ideal if ideal else 0.}

def validar(base):
    corpus=ROOT/'datos/literature_raw_corpus.tsv'
    queries=read(base/'queries.tsv'); qrels=read(base/'qrels.tsv')
    if len(queries)!=15 or Counter(q['difficulty_level'] for q in queries)!={'1':5,'2':5,'3':5}:
        raise ValueError('Se requieren cinco consultas por nivel y quince en total.')
    qids={q['query_id'] for q in queries}; ids={r['fragment_id'] for r in read(corpus)}
    if len(qids)!=15: raise ValueError('Consultas duplicadas.')
    judgments=defaultdict(dict)
    for row in qrels:
        q,d,v=row['query_id'],row['document_id'],int(row['relevance'])
        if q not in qids or d not in ids or v not in (1,2) or d in judgments[q]:
            raise ValueError('Qrels inválidos, desconocidos o duplicados.')
        judgments[q][d]=v
    for q in qids:
        if not 10<=len(judgments[q])<=15 or set(judgments[q].values())!={1,2}:
            raise ValueError('Se requieren 10–15 relevantes y una combinación de 1 y 2 por consulta.')
    return queries,judgments

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--benchmark',type=Path,default=BASE)
    parser.add_argument('--salida',type=Path,default=ROOT/'resultados')
    args=parser.parse_args(); base=args.benchmark.resolve(); out=args.salida.resolve()
    out.mkdir(parents=True,exist_ok=True)
    queries,judgments=validar(base)
    spec=importlib.util.spec_from_file_location('buscador_benchmark',ROOT/'scripts/09_recuperar_fragmentos.py')
    ir=importlib.util.module_from_spec(spec); spec.loader.exec_module(ir)
    engine=ir.Buscador()
    per_query=[]; summaries=[]; diagnostic=[]
    for field in ('titulo','texto'):
        for n in (1,2):
            for representation in ('frecuencia','binaria','tfidf'):
                config=f'{field}_{n}_{representation}'; rankings=[]; local=[]
                for q in queries:
                    result=engine.buscar(q['query'],field,n,representation,q['query_id'])
                    hits=result['resultados']; metrics=metricas([r['document_id'] for r in hits],judgments[q['query_id']])
                    row=dict(configuracion=config,query_id=q['query_id'],difficulty_level=q['difficulty_level'],**metrics)
                    per_query.append(row); local.append(row)
                    rankings.extend({k:h[k] for k in ['query_id','document_id','rank','score']} for h in hits)
                    diagnostic.append(dict(configuracion=config,query_id=q['query_id'],consulta_normalizada=result['consulta_normalizada'],
                        documentos_similitud_positiva=result['documentos_similitud_positiva'],avisos=result['avisos'],
                        relevantes_juzgados_top10=sum(h['document_id'] in judgments[q['query_id']] for h in hits),
                        no_juzgados_top10=sum(h['document_id'] not in judgments[q['query_id']] for h in hits)))
                write(out/config/'rankings.tsv',rankings,['query_id','document_id','rank','score'])
                write(out/config/'metricas.tsv',local,list(local[0]))
                mean={key:sum(r[key] for r in local)/15 for key in ['P@10','R@10','F1@10','RR','nDCG@10']}
                mean['MRR']=mean.pop('RR')
                summaries.append(dict(configuracion=config,**mean))
                print(config, json.dumps(mean,ensure_ascii=False))
    write(out/'metricas_por_consulta.tsv',per_query,list(per_query[0]))
    write(out/'comparacion_configuraciones.tsv',summaries,list(summaries[0]))
    by_level=[]
    for config in [x['configuracion'] for x in summaries]:
        for level in ('1','2','3'):
            selected=[r for r in per_query if r['configuracion']==config and r['difficulty_level']==level]
            values={key:sum(r[key] for r in selected)/len(selected) for key in ['P@10','R@10','F1@10','RR','nDCG@10']}
            values['MRR']=values.pop('RR'); by_level.append(dict(configuracion=config,difficulty_level=level,**values))
    write(out/'metricas_por_nivel.tsv',by_level,list(by_level[0]))
    (out/'diagnostico_consultas.json').write_text(json.dumps(diagnostic,ensure_ascii=False,indent=2),encoding='utf-8')
    baseline=[r for r in per_query if r['configuracion']==BASELINE]
    best=sorted(baseline,key=lambda r:(-r['nDCG@10'],r['query_id']))[:5]
    best_ids={r['query_id'] for r in best}
    worst=sorted([r for r in baseline if r['query_id'] not in best_ids],key=lambda r:(r['nDCG@10'],r['query_id']))[:5]
    result=dict(estado='Resultados provisionales sobre benchmark de desarrollo con juicios IA; validación humana pendiente',
        consultas=15,juicios=sum(map(len,judgments.values())),configuraciones=12,rankings=180,resultados_top10=1800,
        baseline=BASELINE,criterio_analisis='Cinco mayores y cinco menores nDCG@10 de la baseline, con desempate por query_id y sin solapamiento',
        mejores_relativas=best,peores_relativas=worst,configuraciones_resumen=summaries,
        hash_queries=sha(base/'queries.tsv'),hash_qrels=sha(base/'qrels.tsv'),
        hash_corpus=sha(ROOT/'datos/literature_raw_corpus.tsv'),
        advertencia='Ausentes de qrels son no juzgados tratados como 0 solo para este ejercicio. Métricas relativas a un conjunto incompleto, no exactitud sobre todo el corpus.')
    (out/'resumen.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Resultados guardados en',out)
    return 0

if __name__=='__main__':
    try: sys.exit(main())
    except (ValueError,OSError,KeyError) as exc:
        print('ERROR:',exc,file=sys.stderr); sys.exit(1)
