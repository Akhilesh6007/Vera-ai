"""Simple per-turn language adaptation without machine-translated prose."""
import re
def detect_language(message='',preferred=None,history=()):
    text=(message or '').lower()
    if re.search('[\u0900-\u097f]',message or ''):return 'hi'
    if any(w in text.split() for w in ('hai','hain','nahi','kya','chahiye','kripya','haan','ji','mujhe','aap','karna')):return 'hi-en'
    pref=str(preferred or '').lower()
    if 'hi-en' in pref or 'hinglish' in pref:return 'hi-en'
    if pref in ('hi','hindi'):return 'hi'
    if pref.startswith('en'):return 'en'
    return 'en'
