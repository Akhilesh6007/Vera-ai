import json,pathlib,sys
from bot import compose
from validator import validate
ROOT=pathlib.Path(__file__).parent
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def index(folder):
    out={}
    if folder.exists():
        for p in folder.glob('*.json'):
            d=read(p)
            for key in ('id','merchant_id','customer_id','slug'):
                if d.get(key):out[str(d[key])]=d
            out[p.stem]=d
    return out
if __name__=='__main__':
    ds=ROOT/'dataset'; manifest=ds/'test_pairs.json'
    if not manifest.exists():print('Dataset/canonical cases absent. No fabricated submission rows generated.');sys.exit(0)
    cats=index(ds/'categories');mers=index(ds/'merchants');trgs=index(ds/'triggers');cuss=index(ds/'customers');out=[]
    demo_rows=[]
    for c in read(manifest).get('pairs',[]):
        cust=cuss.get(c.get('customer_id'));mer=mers.get(c.get('merchant_id'),{});trg=trgs.get(c.get('trigger_id'),{})
        cat=cats.get(mer.get('category_slug'),{})
        trg=dict(trg);trg['first_outbound']=not bool(mer.get('conversation_history'))
        ref=trg.get('payload',{}).get('top_item_id') or trg.get('payload',{}).get('digest_item_id')
        if ref:
            def find_ref(obj):
                if isinstance(obj,dict):
                    if str(obj.get('id'))==str(ref):return obj
                    for value in obj.values():
                        found=find_ref(value)
                        if found:return found
                if isinstance(obj,list):
                    for value in obj:
                        found=find_ref(value)
                        if found:return found
                return None
            match=find_ref(cat)
            if match:
                trg['payload']['top_item']=match
                trg['payload']['digest_item']=match
        r={'test_id':c['test_id'],**compose(cat,mer,trg,cust)}
        errors=validate(r,cust if cust is not None else ({} if trg.get('scope')=='customer' else None))
        if errors:r['validation_errors']=errors
        out.append(r)
        identity=mer.get('identity',{})
        demo_rows.append({'test_id':c['test_id'],'merchant':identity.get('name',mer.get('merchant_id')),'locality':identity.get('locality',identity.get('city','')),'category':cat.get('display_name',mer.get('category_slug','')),'trigger':trg.get('kind',''),'send_as':r['send_as'],'body':r['body']})
    (ROOT/'submission.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in out),encoding='utf-8');print(f'Wrote {len(out)} submission rows')
    (ROOT/'demo-data.json').write_text(json.dumps(demo_rows,ensure_ascii=False,indent=2),encoding='utf-8')
