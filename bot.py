"""Deterministic, context-grounded Vera challenge composer."""
from typing import Optional

def _find(obj, terms):
    if isinstance(obj, dict):
        for k,v in obj.items():
            if any(t in k.lower() for t in terms) and v not in (None, '', [], {}): return v
        for v in obj.values():
            found=_find(v,terms)
            if found is not None:return found
    elif isinstance(obj,list):
        for v in obj:
            found=_find(v,terms)
            if found is not None:return found
    return None

def compose(category:dict, merchant:dict, trigger:dict, customer:Optional[dict]=None)->dict:
    category=category or {}; merchant=merchant or {}; trigger=trigger or {}; customer=customer or {}
    typ=str(trigger.get('kind') or trigger.get('type') or trigger.get('trigger_type') or 'business update')
    is_customer=bool(customer) or 'customer' in str(trigger.get('scope','')).lower()
    name=_find(customer if is_customer else merchant,['owner_first_name','name','display_name','business_name']) or 'there'
    locality=_find(merchant,['locality','area','city'])
    payload=trigger.get('payload',{}) if isinstance(trigger.get('payload',{}),dict) else {}
    fact=_find(payload,['headline','finding','title','event','change','reason','top_item']) or _find(trigger,['headline','finding','title','event','change'])
    signal=_find(merchant,['ctr','rating','reviews','views','searches','calls','directions','orders','revenue','profile_completion'])
    offer=_find(merchant,['title'])
    key=str(trigger.get('suppression_key') or f"{typ}:{merchant.get('merchant_id',name)}:{customer.get('customer_id','')}")
    low=typ.lower()
    if is_customer:
        merchant_name=_find(merchant,['name','business_name']) or 'your local business'
        due=payload.get('due_date') or payload.get('appointment_date')
        service=payload.get('service_due')
        if low=='appointment_tomorrow':
            body=f"Hi {name}, a reminder from {merchant_name}: you have an appointment tomorrow. Reply here if you need to change the time."
        elif 'refill' in low:
            when=payload.get('stock_runs_out_iso')
            body=f"Hi {name}, a refill reminder from {merchant_name}." + (f" Your current supply may run out by {when[:10]}." if isinstance(when,str) else '') + " Reply here if you’d like the pharmacy to help."
        elif 'lapsed' in low:
            body=f"Hi {name}, we’d be happy to welcome you back to {merchant_name}. Let us know if you’d like help finding a suitable time."
        else:
            body=f"Hi {name}, a note from {merchant_name}: {service.replace('_',' ') if isinstance(service,str) else typ.replace('_',' ')} is due" + (f" on {due}" if due else '') + "."
        slots=payload.get('available_slots') or []
        slot_labels=[s.get('label') for s in slots if isinstance(s,dict) and s.get('label')]
        if slot_labels: body+=f" Available times: {', '.join(slot_labels[:2])}."
        elif offer: body+=f" Available service: {offer}."
        cta='open_ended' if slot_labels else 'open_ended'
        sender='merchant_on_behalf'
    else:
        place=f" in {locality}" if locality else ''
        if low=='active_planning_intent':
            topic=str(payload.get('intent_topic','business idea')).replace('_',' ')
            body=f"{name}, picking up your {topic} idea. I can sketch a first version using only the details you confirm. What per-person budget should I work to?"
        elif low=='cde_opportunity':
            item=payload.get('digest_item') or {}
            title=item.get('title') if isinstance(item,dict) else None
            date=item.get('date') if isinstance(item,dict) else None
            fee=payload.get('fee')
            body=f"{name}, {title or 'a dental education opportunity'} is coming up{f' on {date[:10]}' if isinstance(date,str) else ''}."
            if fee: body+=f" Fee: {str(fee).replace('_',' ')}."
            if item.get('summary'): body+=f" {item['summary']}"
            body+=' Want me to share the details?'
        elif low=='category_seasonal':
            trends=payload.get('trends') or []
            body=f"{name}, the summer demand update is relevant to your pharmacy{place}."
            if trends: body+=f" The supplied signal is {str(trends[0]).replace('_',' ')}."
            body+=' Want a short shelf-priority summary?'
        if any(x in low for x in ('research','digest')):
            body=f"{name}, a new {typ.replace('_',' ')} is relevant to your business{place}."
            if fact: body+=f" {fact}."
            body+=' Want me to pull out the most useful takeaway?'
        elif any(x in low for x in ('dip','spike','perf')):
            delta=payload.get('delta_pct'); metric=payload.get('metric') or 'performance'; baseline=payload.get('vs_baseline'); window=payload.get('window')
            detail=f"{metric} changed {abs(delta):.0%}" if isinstance(delta,(int,float)) else (f"({signal})" if signal else '')
            direction='down' if isinstance(delta,(int,float)) and delta<0 else 'up'
            body=f"{name}, your {metric} are {direction} {detail}{f' over {window}' if window else ''}{f' (baseline: {baseline})' if baseline is not None else ''}{place}. Want me to break down the change and suggest one next step?"
        elif any(x in low for x in ('festival','weather','event','news','trend','competitor','regulation')):
            body=f"{name}, {typ.replace('_',' ')}{f' — {fact}' if fact else ''} may matter for your business{place}."
            if offer: body+=f" Your current offer/service: {offer}."
            body+=' Want a short, category-specific plan?'
        elif low not in ('active_planning_intent','cde_opportunity','category_seasonal'):
            body=f"{name}, I’m reaching out about {typ.replace('_',' ')}{place}."
            if fact: body+=f" {fact}."
            body+=' Want me to look at the next step?'
        cta='YES/STOP' if '?' in body else 'none'; sender='vera'
    return {'body':body,'cta':cta,'send_as':sender,'suppression_key':key,'rationale':f"Uses {typ} and supplied context only; no external facts added."}
