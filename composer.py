"""LLM-backed optional composer with bounded repair and deterministic fallback."""
import json,os,logging
from bot import compose as fallback_compose
from context_builder import select_context
from llm.providers import create_provider
from prompts import SYSTEM_PROMPT,COMPOSER_VERSION
from validator import validate_grounding

log=logging.getLogger('vera.composer')
def _parse(text):
    text=text.strip()
    if text.startswith('```'):
        text=text.split('\n',1)[-1].rsplit('```',1)[0].strip()
    data=json.loads(text)
    if not isinstance(data,dict):raise ValueError('model response was not a JSON object')
    return data
def compose_message(category,merchant,trigger,customer=None,history=()):
    fallback=fallback_compose(category,merchant,trigger,customer)
    if os.getenv('LLM_ENABLED','').lower() not in ('1','true','yes'):return fallback
    provider=create_provider()
    if provider is None:return fallback
    contexts={'category':category,'merchant':merchant,'trigger':trigger,'customer':customer}
    selected=select_context(category,merchant,trigger,customer,history)
    user=json.dumps({'composer_version':COMPOSER_VERSION,'contexts':selected},ensure_ascii=False,default=str)
    for attempt in range(3):
        try:
            prompt=user if attempt==0 else user+'\n\nRepair the prior output. It failed: '+', '.join(errors)+'. Return only valid JSON with required fields.'
            candidate=_parse(provider.complete(SYSTEM_PROMPT,prompt))
            errors=validate_grounding(candidate,contexts)
            if not errors:return candidate
        except Exception as exc:
            errors=[str(exc)];log.warning('Optional LLM attempt %d failed; retaining grounded fallback (%s)',attempt+1,type(exc).__name__)
    return fallback
