"""Stateful FastAPI service implementing magicpin's five-endpoint contract."""
from __future__ import annotations
import json,os,re,time,logging
from datetime import datetime,timezone,timedelta
from pathlib import Path
from typing import Any
from fastapi import FastAPI,HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel,Field
from context_store import ContextStore,StaleVersionError
from conversation_store import ConversationStore
from bot import compose
from validator import validate,validate_grounding
from intent import detect_intent,is_automated,normalize_message
from conversation_engine import transition
from language import detect_language
from router import route_trigger
from context_builder import select_context
from prompts import SYSTEM_PROMPT,COMPOSER_VERSION
from composer import compose_message

logging.basicConfig(level=os.getenv('LOG_LEVEL','INFO'));log=logging.getLogger('vera')
ROOT=Path(__file__).parent;START=time.monotonic();contexts=ContextStore();conversations=ConversationStore()
app=FastAPI(title='Vera AI Challenge API',version='1.0.0')
app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:8765','http://localhost:8765','http://127.0.0.1:5173','http://localhost:5173'],allow_methods=['GET','POST','OPTIONS'],allow_headers=['*'])

@app.exception_handler(RequestValidationError)
async def invalid_request(_request,exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=400,content={'accepted':False,'reason':'invalid_request','details':'Request fields are missing or malformed.'})

@app.middleware('http')
async def telemetry(request,call_next):
    start=time.monotonic();failed=False
    try:return await call_next(request)
    except Exception:
        failed=True;raise
    finally:conversations.record_request(request.url.path,(time.monotonic()-start)*1000,failed)

class ContextPush(BaseModel):
    scope:str;context_id:str;version:int=Field(ge=1);payload:dict[str,Any];delivered_at:str|None=None
class TickRequest(BaseModel):
    now:str;available_triggers:list[str]=Field(default_factory=list)
class ReplyRequest(BaseModel):
    conversation_id:str;merchant_id:str|None=None;customer_id:str|None=None;from_role:str='merchant';message:str;received_at:str|None=None;turn_number:int=Field(default=1,ge=1)

def _load_demo_contexts():
    if os.getenv('DEMO_PRELOAD_DATASET','').lower() not in ('1','true','yes'):return
    ds=ROOT/'dataset'
    for scope,folder,key in [('category','categories','slug'),('merchant','merchants','merchant_id'),('customer','customers','customer_id'),('trigger','triggers','id')]:
        for p in (ds/folder).glob('*.json'):
            payload=json.loads(p.read_text(encoding='utf-8'));cid=str(payload.get(key,p.stem));contexts.put(scope,cid,1,payload)
_load_demo_contexts()

@app.get('/v1/healthz')
def healthz():return {'status':'ok','uptime_seconds':int(time.monotonic()-START),'contexts_loaded':contexts.counts()}

@app.get('/v1/metadata')
def metadata():
    return {'team_name':os.getenv('TEAM_NAME','Vera Challenge Demo'),'team_members':[x.strip() for x in os.getenv('TEAM_MEMBERS','').split(',') if x.strip()],'model':os.getenv('LLM_MODEL') or 'deterministic-offline','approach':'stateful context router + grounded deterministic composer + validation','contact_email':os.getenv('TEAM_EMAIL',''),'version':'1.0.0','submitted_at':os.getenv('SUBMITTED_AT','')}

@app.post('/v1/context')
def push_context(body:ContextPush):
    if body.scope not in ('category','merchant','customer','trigger'):raise HTTPException(400,detail={'accepted':False,'reason':'invalid_scope','details':'scope must be one of category, merchant, customer, trigger'})
    try:changed=contexts.put(body.scope,body.context_id,body.version,body.payload,body.delivered_at)
    except StaleVersionError as e:raise HTTPException(409,detail={'accepted':False,'reason':'stale_version','current_version':e.current_version})
    except ValueError as e:raise HTTPException(400,detail={'accepted':False,'reason':'invalid_context','details':str(e)})
    stored=contexts.record(body.scope,body.context_id)
    ack=re.sub(r'[^A-Za-z0-9_-]','_',body.context_id)[:72]
    return {'accepted':True,'ack_id':f'ack_{ack}_v{body.version}','stored_at':body.delivered_at or datetime.now(timezone.utc).isoformat(),'unchanged':not changed}

def _expired(trigger,now):
    exp=trigger.get('expires_at')
    if not exp:return False
    try:return _parse_utc(exp) < _parse_utc(now)
    except (ValueError,TypeError):return False

def _parse_utc(value):
    parsed=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if parsed.tzinfo is None:parsed=parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)

def _resolve_customer_consent(customer,trigger):
    if trigger.get('scope')!='customer':return True
    if not customer:return False
    consent=customer.get('consent') or {};scopes=consent.get('scope') or []
    kind=str(trigger.get('kind','')).lower()
    required='refill_reminders' if 'refill' in kind else 'appointment_reminders' if 'appointment' in kind else 'recall_reminders'
    aliases={'recall_reminders':{'recall_reminders','recall_alerts'},'appointment_reminders':{'appointment_reminders'},'refill_reminders':{'refill_reminders','treatment_followup'}}
    return bool(set(scopes).intersection(aliases[required]))

@app.post('/v1/tick')
def tick(body:TickRequest):
    actions=[]
    try:now_dt=_parse_utc(body.now)
    except (ValueError,TypeError):now_dt=None
    for tid in body.available_triggers:
        if len(actions)>=20:break
        trigger=contexts.get('trigger',tid)
        if not trigger:continue
        mid=trigger.get('merchant_id');merchant=contexts.get('merchant',mid) if mid else None
        if not merchant:continue
        if conversations.is_opted_out(mid):continue
        cid=trigger.get('customer_id');customer=contexts.get('customer',cid) if cid else None
        if trigger.get('scope')=='customer':
            if not customer or customer.get('merchant_id')!=mid or not _resolve_customer_consent(customer,trigger):continue
        elif cid:
            continue
        slug=merchant.get('category_slug') or (merchant.get('identity') or {}).get('category_slug') or (customer or {}).get('category_slug')
        category=contexts.get('category',slug) if slug else None
        if not category:continue
        if _expired(trigger,body.now):continue
        key=str(trigger.get('suppression_key') or tid)
        existing=next((c for c in conversations.all() if c.get('status') in ('open','waiting') and c.get('trigger_id')==tid),None)
        resumed=False
        if existing:
            if existing.get('status')!='waiting' or not now_dt:continue
            try:due=_parse_utc(existing.get('next_eligible_at')) if existing.get('next_eligible_at') else None
            except (ValueError,TypeError):due=None
            if not due or now_dt<due:continue
            resumed=True;conversations.clear_suppression(key)
        elif conversations.seen_suppression(key):continue
        strategy=route_trigger(trigger)
        history=[m.get('body','') for m in (existing or {}).get('messages',[]) if m.get('role') in ('merchant','customer','vera')]
        result=compose_message(category,merchant,trigger,customer,history)
        if resumed and any(m.get('role')=='vera' and m.get('body')==result.get('body') for m in existing.get('messages',[])):
            kind_label=str(trigger.get('kind','update')).replace('_',' ')
            result['body']=f"Following up on my earlier {kind_label} note. If the owner is available now, I can help with the next step."
        problems=validate_grounding(result,{'category':category,'merchant':merchant,'trigger':trigger,'customer':customer if customer is not None or trigger.get('scope')=='customer' else None})
        if problems:
            log.warning('Composer validation failed for trigger %s: %s',tid,problems);continue
        language=detect_language('',(customer or {}).get('identity',{}).get('language_pref') or (merchant.get('identity') or {}).get('languages',['en'])[0])
        token=re.sub(r'[^a-z0-9]+','_',key.lower()).strip('_')[-28:]
        conv_id=f"conv_{mid}_{token}"
        conv=conversations.create(conv_id,merchant_id=mid,customer_id=cid,scope=trigger.get('scope','merchant'),trigger_id=tid,strategy=strategy,language=language,last_cta=result['cta'],suppression_keys=[key])
        if resumed:conversations.update(conv_id,status='open',next_eligible_at=None,last_cta=result['cta'],strategy=strategy)
        conversations.add_message(conv_id,'vera',result['body'],cta=result['cta'])
        conversations.mark_suppression(key)
        name=((customer or {}).get('identity') or {}).get('name') or ((merchant.get('identity') or {}).get('owner_first_name')) or ((merchant.get('identity') or {}).get('name')) or 'there'
        kind=re.sub(r'[^a-z0-9]+','_',str(trigger.get('kind','update')).lower()).strip('_')[:32]
        params=[name,result['body']]
        actions.append({'conversation_id':conv_id,'merchant_id':mid,'customer_id':cid,'send_as':result['send_as'],'trigger_id':tid,'template_name':f'vera_{kind}_v1','template_params':params,'body':result['body'],'cta':result['cta'],'suppression_key':key,'rationale':result['rationale']})
    return {'actions':actions}

@app.post('/v1/reply')
def reply(body:ReplyRequest):
    convo=conversations.get(body.conversation_id)
    if convo is None:convo=conversations.create(body.conversation_id,merchant_id=body.merchant_id,customer_id=body.customer_id,scope='customer' if body.customer_id else 'merchant')
    if body.merchant_id and convo.get('merchant_id') not in (None,body.merchant_id):raise HTTPException(400,detail='merchant_id does not match conversation')
    if body.customer_id and convo.get('customer_id') not in (None,body.customer_id):raise HTTPException(400,detail='customer_id does not match conversation')
    if body.from_role not in ('merchant','customer'):raise HTTPException(400,detail='from_role must be merchant or customer')
    if convo.get('status') in ('ended','closed'):
        return {'action':'end','rationale':'Conversation is already closed; no further message was sent.'}
    last_turn=int(convo.get('last_inbound_turn') or 0)
    if body.turn_number==last_turn and convo.get('last_transition'):
        if normalize_message(body.message)!=convo.get('last_inbound_text'):
            raise HTTPException(409,detail={'reason':'duplicate_turn_mismatch','current_turn':last_turn})
        return dict(convo['last_transition'])
    if body.turn_number<last_turn:
        raise HTTPException(409,detail={'reason':'stale_turn','current_turn':last_turn})

    prior_inbound=[m.get('body','') for m in convo.get('messages',[]) if m.get('role') in ('merchant','customer')]
    intent=detect_intent(body.message)
    auto= intent=='auto_reply' or is_automated(body.message,prior_inbound)
    auto_count=conversations.auto_count(body.merchant_id or convo.get('merchant_id') or 'unknown',body.message) if auto else int(convo.get('auto_reply_count') or 0)
    lang=detect_language(body.message,convo.get('language'))
    result=transition(message=body.message,turn_number=body.turn_number,status=convo.get('status','open'),prior_messages=prior_inbound,auto_reply_count=auto_count-1 if auto else 0,language=lang)
    conversations.add_message(body.conversation_id,body.from_role,body.message,turn_number=body.turn_number,received_at=body.received_at)
    if result['action']=='send':
        conversations.add_message(body.conversation_id,'vera',result['body'],cta=result.get('cta','open_ended'))
    if result.get('intent')=='stop':
        conversations.mark_optout(body.merchant_id or convo.get('merchant_id'))
        for key in convo.get('suppression_keys',[]):conversations.mark_suppression(key)
    lang=detect_language(body.message,convo.get('language'))
    result['language']=lang
    public_result={k:v for k,v in result.items() if k not in ('status','intent','language','auto_reply_detected','auto_reply_count')}
    next_eligible_at=None
    if result['action']=='wait':
        try:received=_parse_utc(body.received_at) if body.received_at else datetime.now(timezone.utc)
        except (ValueError,TypeError):received=datetime.now(timezone.utc)
        next_eligible_at=(received+timedelta(seconds=result['wait_seconds'])).isoformat()
    conversations.update(body.conversation_id,status=result.get('status','open'),intent=result.get('intent'),language=lang,next_eligible_at=next_eligible_at,
        turn_number=body.turn_number+1,last_inbound_turn=body.turn_number,last_inbound_text=normalize_message(body.message),last_transition=public_result,
        auto_reply_detected=bool(convo.get('auto_reply_detected') or result.get('auto_reply_detected')),
        auto_reply_count=auto_count if auto else int(convo.get('auto_reply_count') or 0))
    return public_result

@app.get('/v1/dashboard')
def dashboard():
    data={scope:contexts.all(scope) for scope in ('category','merchant','customer','trigger')}
    return {'status':'ok','counts':contexts.counts(),'contexts':data,'conversations':conversations.all(),'metrics':conversations.metrics(),'evaluation':{'source':'local heuristic','official_score':None}}

@app.get('/v1/context/{scope}/{context_id}')
def context_detail(scope:str,context_id:str):
    rec=contexts.record(scope,context_id)
    if not rec:raise HTTPException(404,detail='context not found')
    return {'scope':scope,'context_id':context_id,**rec}

@app.get('/v1/conversations')
def list_conversations():return {'conversations':conversations.all()}

@app.get('/v1/evaluation')
def evaluation():
    try:
        with (ROOT/'submission.jsonl').open(encoding='utf-8') as f:rows=[json.loads(x) for x in f if x.strip()]
    except OSError:rows=[]
    return {'label':'Local Heuristic Evaluation · Not Official Judge Score','cases':rows,'valid':sum(not bool(r.get('validation_errors')) for r in rows),'total':len(rows),'warnings':[]}

class ComposeRequest(BaseModel):
    merchant_id:str;trigger_id:str;customer_id:str|None=None;category_id:str|None=None
@app.post('/v1/compose')
def compose_preview(body:ComposeRequest):
    merchant=contexts.get('merchant',body.merchant_id)
    trigger=contexts.get('trigger',body.trigger_id)
    customer=contexts.get('customer',body.customer_id) if body.customer_id else None
    if customer and customer.get('merchant_id')!=body.merchant_id:raise HTTPException(400,detail='customer context belongs to a different merchant')
    if not merchant or not trigger:raise HTTPException(404,detail='merchant or trigger context not found')
    category_id=body.category_id or merchant.get('category_slug')
    category=contexts.get('category',category_id) if category_id else None
    if not category:raise HTTPException(404,detail='category context not found')
    history=[m.get('body','') for m in (merchant.get('conversation_history') or [])]
    result=compose_message(category,merchant,trigger,customer,history)
    issues=validate_grounding(result,{'category':category,'merchant':merchant,'trigger':trigger,'customer':customer})
    return {'message':result,'validation':{'valid':not issues,'issues':issues,'pipeline':['context_loaded','trigger_resolved','language_detected','strategy_selected','composer_generated','fact_validation','cta_validation']},'strategy':route_trigger(trigger),'composer_version':COMPOSER_VERSION}

@app.get('/v1/system')
def system_status():
    provider=os.getenv('LLM_PROVIDER','').strip().lower();enabled=os.getenv('LLM_ENABLED','').lower() in ('1','true','yes')
    return {'challenge_mode':True,'llm_enabled':enabled and bool(provider),'provider':provider or 'offline','model':os.getenv('LLM_MODEL') or 'deterministic-offline','temperature':0,'dataset_path':'dataset/','feature_flags':{'customer_consent_gate':True,'template_first_touch':True,'deterministic_fallback':True},'composer_version':COMPOSER_VERSION}
