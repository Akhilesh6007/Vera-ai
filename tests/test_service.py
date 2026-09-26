import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import app as service

class ServiceTests(unittest.TestCase):
    def setUp(self):self.client=TestClient(service.app)
    def test_health_and_metadata(self):
        self.assertEqual(self.client.get('/v1/healthz').json()['status'],'ok')
        self.assertIn('model',self.client.get('/v1/metadata').json())
    def test_context_versioning(self):
        payload={'slug':'test'};body={'scope':'category','context_id':'unittest-category','version':1,'payload':payload}
        self.assertTrue(self.client.post('/v1/context',json=body).json()['accepted'])
        same=self.client.post('/v1/context',json=body);self.assertEqual(same.status_code,200);self.assertTrue(same.json()['unchanged'])
        higher={**body,'version':2,'payload':{'slug':'test','v':2}};self.assertTrue(self.client.post('/v1/context',json=higher).json()['accepted'])
        stale=self.client.post('/v1/context',json=body);self.assertEqual(stale.status_code,409)
        self.assertEqual(service.contexts.get('category','unittest-category')['v'],2)
    def test_invalid_scope(self):
        res=self.client.post('/v1/context',json={'scope':'bad','context_id':'bad','version':1,'payload':{}});self.assertEqual(res.status_code,400)
    def test_tick_suppression_and_customer_route(self):
        data=service.ROOT/'dataset';import json
        merchant=json.loads((data/'merchants/m_001_drmeera_dentist_delhi.json').read_text(encoding='utf-8'))
        category=json.loads((data/'categories/dentists.json').read_text(encoding='utf-8'))
        trigger=json.loads((data/'triggers/trg_001_research_digest_dentists.json').read_text(encoding='utf-8'))
        for scope,cid,p in [('category','dentists',category),('merchant',merchant['merchant_id'],merchant),('trigger',trigger['id'],trigger)]:
            service.contexts.put(scope,cid,1,p)
        result=self.client.post('/v1/tick',json={'now':'2026-04-26T10:35:00Z','available_triggers':[trigger['id']]}).json()
        self.assertEqual(len(result['actions']),1);self.assertEqual(result['actions'][0]['send_as'],'vera')
        again=self.client.post('/v1/tick',json={'now':'2026-04-26T10:40:00Z','available_triggers':[trigger['id']]}).json();self.assertEqual(again['actions'],[])
    def test_compose_preview(self):
        data=service.ROOT/'dataset';import json
        merchant=json.loads((data/'merchants/m_001_drmeera_dentist_delhi.json').read_text(encoding='utf-8'));trigger=json.loads((data/'triggers/trg_001_research_digest_dentists.json').read_text(encoding='utf-8'));category=json.loads((data/'categories/dentists.json').read_text(encoding='utf-8'))
        for scope,cid,p in [('category','dentists',category),('merchant',merchant['merchant_id'],merchant),('trigger',trigger['id'],trigger)]:service.contexts.put(scope,cid,1,p)
        r=self.client.post('/v1/compose',json={'merchant_id':merchant['merchant_id'],'trigger_id':trigger['id']});self.assertEqual(r.status_code,200);self.assertTrue(r.json()['validation']['valid'])
    def test_reply_stop_and_intent(self):
        r=self.client.post('/v1/reply',json={'conversation_id':'unit-stop','merchant_id':'m-test','message':'Stop messaging me','turn_number':2}).json();self.assertEqual(r['action'],'end')
        r=self.client.post('/v1/reply',json={'conversation_id':'unit-join','merchant_id':'m-test','message':'Mujhe magicpin join karna hai','turn_number':2}).json();self.assertEqual(r['action'],'send');self.assertIn('onboarding',r['body'].lower())
        r=self.client.post('/v1/reply',json={'conversation_id':'unit-go-ahead','merchant_id':'m-test','message':'Ok lets do it. Whats next?','turn_number':2}).json();self.assertEqual(r['action'],'send');self.assertIn('next',r['body'].lower())
    def test_auto_reply_backoff_then_end(self):
        body={'conversation_id':'unit-auto','merchant_id':'m-auto','message':'Thank you for contacting us! Our team will respond shortly.','turn_number':2}
        self.assertEqual(self.client.post('/v1/reply',json=body).json()['action'],'wait')
        body['turn_number']=3
        self.assertEqual(self.client.post('/v1/reply',json=body).json()['action'],'end')

if __name__=='__main__':unittest.main()
