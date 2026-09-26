import pathlib
ROOT=pathlib.Path(__file__).parent
if not (ROOT/'dataset'/'test_pairs.json').exists():
    print('Local heuristic evaluation skipped: dataset and canonical cases are absent (not an official score).')
else:
    import json,subprocess,sys
    from bot import compose
    from validator import validate
    sys.path.insert(0,str(ROOT))
    from generate_submission import index,read
    ds=ROOT/'dataset'; cats=index(ds/'categories'); mers=index(ds/'merchants'); trgs=index(ds/'triggers'); cuss=index(ds/'customers')
    pairs=read(ds/'test_pairs.json')['pairs']; seen=set(); stats={'valid_outputs':0,'invalid_outputs':0,'empty_outputs':0,'duplicate_outputs':0,'customer_routing_errors':0}
    for c in pairs:
        mer=mers[c['merchant_id']];trg=trgs[c['trigger_id']];cust=cuss.get(c.get('customer_id'));cat=cats[mer.get('category_slug')]
        r=compose(cat,mer,trg,cust);is_customer=cust is not None or trg.get('scope')=='customer';errs=validate(r,cust if cust is not None else ({} if is_customer else None));stats['valid_outputs']+=not bool(errs);stats['invalid_outputs']+=bool(errs);stats['empty_outputs']+=not bool(r['body'].strip());stats['duplicate_outputs']+=r['body'] in seen;seen.add(r['body']);stats['customer_routing_errors']+=r['send_as']!=('merchant_on_behalf' if is_customer else 'vera')
        print(f"{c['test_id']} | {mer.get('identity',{}).get('name')} | {trg.get('kind')} | {r['cta']} | {'PASS' if not errs else ', '.join(errs)}")
    print('Local heuristic evaluation (not official scores):',json.dumps(stats,indent=2))
