STOP=('stop','unsubscribe','not interested','dont contact','don’t contact','nahi chahiye','abhi nahi')
JOIN=('join','sign up','signup','register','go ahead','yes','i want to join','magicpin join')
AUTO=('thank you for contacting','thank you for your message','we will get back','team will contact','automated assistant','office hours')
def detect_intent(message):
    t=message.lower().strip()
    if any(x in t for x in STOP): return 'stop'
    if any(x in t for x in JOIN): return 'join'
    if any(x in t for x in AUTO): return 'auto_reply'
    if '?' in t:return 'question'
    return 'other'
def respond(state,merchant_message):
    state=state if isinstance(state,dict) else {}; hist=state.setdefault('previous_messages',[]); intent=detect_intent(merchant_message);hist.append(merchant_message)
    if intent=='stop': state['stop_requested']=True; body='Understood. I’ll stop messaging you.'
    elif state.get('stop_requested'): body=''
    elif intent=='join': state['merchant_interest']=True;state.setdefault('actions_requested',[]).append('join');body='Great, I’ll move this to the magicpin joining steps. Please share the business name and locality so the team can continue.'
    elif intent=='auto_reply' or sum(x.strip().lower()==merchant_message.strip().lower() for x in hist)>=3:
        state['auto_reply_detected']=True
        if state.get('auto_reply_attempted'): state['stop_requested']=True;body='Understood. I’ll connect with the owner or manager and won’t keep messaging this number.'
        else: state['auto_reply_attempted']=True;body='Thanks. Is the business owner available to review this, or should I follow up another time?'
    elif intent=='question':body='I’ll answer based on the details available for your business. Which part would you like me to clarify?'
    else:body='Got it. What would be most useful to look at next?'
    state['last_intent']=intent;state['message_count']=len(hist)
    return {'body':body,'cta':'YES/STOP' if intent=='join' else 'open_ended','intent':intent,'state':state}
