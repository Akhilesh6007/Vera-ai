import re
REQUIRED={'body','cta','send_as','suppression_key','rationale'}
VALID_CTAS={'YES/STOP','open_ended','none','binary_yes_no','binary_confirm_cancel'}
def validate(result, customer=None):
    if not isinstance(result,dict): return ['output must be an object']
    missing=REQUIRED-set(result)
    if missing:return ['missing required output keys: '+', '.join(sorted(missing))]
    errors=[];body=result.get('body')
    if not isinstance(body,str) or not body.strip():errors.append('empty body')
    elif len(body)>2000:errors.append('body exceeds 2000 characters')
    if result.get('send_as') not in ('vera','merchant_on_behalf'):errors.append('invalid sender')
    expected='merchant_on_behalf' if customer is not None else 'vera'
    if result.get('send_as') in ('vera','merchant_on_behalf') and result['send_as']!=expected:errors.append('sender mismatch')
    if not isinstance(result.get('cta'),str) or result['cta'] not in VALID_CTAS:errors.append('invalid CTA')
    if isinstance(body,str) and len(re.findall(r'\b(?:reply|say|send)\s+(?:yes|stop|no)\b',body,re.I))>1:errors.append('multiple CTAs')
    if not isinstance(result.get('suppression_key'),str) or not result['suppression_key'].strip():errors.append('missing suppression key')
    elif len(result['suppression_key'])>256:errors.append('suppression key exceeds 256 characters')
    if not isinstance(result.get('rationale'),str) or not result['rationale'].strip():errors.append('missing rationale')
    elif len(result['rationale'])>1000:errors.append('rationale exceeds 1000 characters')
    return errors

def validate_grounding(result,contexts):
    """Conservative claim check: numeric/date tokens must occur in source context."""
    contexts=contexts if isinstance(contexts,dict) else {}
    errors=validate(result,contexts.get('customer'))
    source=' '.join(str(contexts.get(k) or {}) for k in ('category','merchant','trigger','customer'))
    body=result.get('body','') if isinstance(result,dict) else ''
    for token in re.findall(r'(?<![A-Za-z])(?:₹\s*)?\d{1,3}(?:,\d{3})+(?:\.\d+)?%?|(?<![A-Za-z])(?:₹\s*)?\d+(?:\.\d+)?%?',body):
        normalized=token.replace('₹','').replace(',','').replace(' ','');clean_source=source.replace(',','').replace(' ','')
        found=normalized in clean_source
        if token.endswith('%'):
            try:found=found or str(float(normalized[:-1])/100).rstrip('0').rstrip('.') in clean_source
            except ValueError:pass
        if normalized and not found:
            errors.append(f'unsupported numeric claim: {token}')
    if re.search(r'\b(?:http|www\.)',body,re.I) and 'http' not in source.lower():errors.append('unsupported URL')
    voice=(contexts.get('category') or {}).get('voice') or {};taboos=voice.get('vocab_taboo') or voice.get('taboos') or []
    for word in taboos:
        if word and str(word).lower() in body.lower():errors.append(f'category taboo: {word}')
    return errors
