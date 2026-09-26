"""Small provider interface; all network access is opt-in by environment."""
import json,os,urllib.request,urllib.error

class LLMProvider:
    model='deterministic-offline'
    def complete(self,system_prompt,user_prompt)->str:raise NotImplementedError

class OpenAIProvider(LLMProvider):
    def __init__(self,key,model,base_url='https://api.openai.com/v1'):
        self.key=key;self.model=model or 'gpt-4o-mini';self.base_url=base_url.rstrip('/')
    def complete(self,system_prompt,user_prompt):
        body=json.dumps({'model':self.model,'temperature':0,'response_format':{'type':'json_object'},'messages':[{'role':'system','content':system_prompt},{'role':'user','content':user_prompt}]}).encode()
        req=urllib.request.Request(self.base_url+'/chat/completions',body,{'Authorization':'Bearer '+self.key,'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=8) as res:return json.loads(res.read())['choices'][0]['message']['content']

class OllamaProvider(LLMProvider):
    def __init__(self,model,url):self.model=model or 'llama3.1';self.url=(url or 'http://localhost:11434').rstrip('/')
    def complete(self,system_prompt,user_prompt):
        body=json.dumps({'model':self.model,'stream':False,'format':'json','options':{'temperature':0},'messages':[{'role':'system','content':system_prompt},{'role':'user','content':user_prompt}]}).encode()
        req=urllib.request.Request(self.url+'/api/chat',body,{'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=8) as res:return json.loads(res.read())['message']['content']

def create_provider():
    name=os.getenv('LLM_PROVIDER','').lower().strip();key=os.getenv('LLM_API_KEY','').strip()
    if name=='openai' and key:return OpenAIProvider(key,os.getenv('LLM_MODEL',''),os.getenv('LLM_BASE_URL','https://api.openai.com/v1'))
    if name=='ollama':return OllamaProvider(os.getenv('LLM_MODEL',''),os.getenv('OLLAMA_URL',''))
    return None
