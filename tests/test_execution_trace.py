import json
import logging
import os
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace as Obj
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from db.models import Base, ChatRun, Feedback, Message, PromptVersion, TrainingSample, Session, KnowledgeVector
from api.main import app
from agent.runtime import ConsultantLoop
from agent.knowledge import search_knowledge
from agent.output_guard import sentence_policy
from agent.tools import build_registry
from harness.guard import StreamingGuard

logging.getLogger('consultant.requests').setLevel(logging.WARNING)

class FakeClient:
    def __init__(self): self.round=0
    def stream(self,messages,tools=None):
        self.round+=1
        user=next((m['content'] for m in reversed(messages) if m['role']=='user'),'')
        if user=='模拟服务失败': raise ConnectionError('secret diagnostic must not appear')
        if self.round==1 and user=='模型转人工':
            call=Obj(index=0,id='model-handoff',function=Obj(name='handoff',arguments=json.dumps({'reason':'事实缺失','summary':'待人工确认'})))
            yield Obj(choices=[Obj(delta=Obj(content=None,tool_calls=[call]))])
        else:
            for part in ['请先说明您的', '学习目标。', '我会结合基础帮您判断。']:
                yield Obj(choices=[Obj(delta=Obj(content=part,tool_calls=[]))])
    def complete(self,messages,json_mode=False):
        if json_mode:
            content='## 铁律\n1. 不报价，先确认意向。\n## 语气\n简短回答，先回应问题。'
            return json.dumps({'candidate':content,'rationale':'针对反馈“回复太长”减少展开。'})
        return '我先了解您的学习目标，具体政策需要进一步确认。'

class ExecutionTraceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.engine=create_engine('sqlite:///'+str(Path(self.temp.name)/'test.db'),connect_args={'check_same_thread':False})
        Base.metadata.create_all(self.engine)
        self.sessions=sessionmaker(bind=self.engine,expire_on_commit=False)
        self.stack=ExitStack()
        for mod in ('api.admin','api.chat','api.main','agent.jobs','agent.prompt_store','agent.samples','agent.knowledge','agent.ticket_store','agent.optimizer'):
            self.stack.enter_context(patch(mod+'.SessionLocal',self.sessions))
        self.stack.enter_context(patch('agent.runtime.QwenClient',FakeClient))
        self.stack.enter_context(patch.dict(os.environ,{'OPTIMIZE_THRESHOLD':'100'}))
        with self.sessions() as db:
            db.add(TrainingSample(question='多少钱',answer='先确认学习意向',reason='不报价',status='approved'))
            db.commit()
        self.client=TestClient(app)

    def tearDown(self):
        self.stack.close();self.engine.dispose();self.temp.cleanup()

    def chat(self,message='你好',rid='request-1'):
        response=self.client.post('/chat',json={'session_id':'test-session','request_id':rid,'message':message})
        self.assertEqual(response.status_code,200)
        rows=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        return response,rows

    def test_tool_pair_context_order_and_force_recall(self):
        loop=ConsultantLoop(client=FakeClient(),session_id='test-session')
        events=list(loop.run_with_tools('模型转人工'))
        starts=[e for e in events if e['type']=='tool_start']
        self.assertEqual(starts[0]['name'],'recall_playbook')
        self.assertEqual(starts[1]['name'],'handoff')
        ends=[e for e in events if e['type']=='tool_end']
        self.assertTrue(ends[1]['result']['ticket_id'])
        self.assertEqual(starts[1]['call_id'],ends[1]['call_id'])
        roles=[m['role'] for m in loop.messages]
        self.assertEqual(roles,['system','user','assistant','tool','assistant','tool','assistant'])

    def test_model_handoff_and_request_idempotency(self):
        response,rows=self.chat('模型转人工')
        self.assertIn('event: handoff',response.text)
        key=next(r['ticket_id'] for r in rows if 'ticket_id' in r)
        tickets=self.client.get('/admin/tickets').json()
        self.assertEqual(tickets[0]['id'],key)
        again=self.client.post('/chat',json={'session_id':'test-session','request_id':'request-1','message':'模型转人工'})
        self.assertEqual(response.text,again.text)
        with self.sessions() as db:
            self.assertEqual(db.query(Message).count(),2)
        self.assertEqual(self.client.post('/chat',json={'session_id':'test-session','request_id':'request-1','message':'不同问题'}).status_code,409)

    def test_fallback_is_traced_and_stream_finishes(self):
        response,rows=self.chat('模拟服务失败')
        self.assertTrue(any(r.get('stage')=='fallback' for r in rows))
        self.assertEqual(rows[-1]['mode'],'fallback')
        self.assertIn('event: done',response.text)
        self.assertNotIn('secret diagnostic',response.text)

    def test_feedback_bound_to_message_and_version(self):
        _,rows=self.chat()
        mid=rows[-1]['message_id']
        self.assertEqual(self.client.post('/admin/feedback',json={'session_id':'wrong','message_id':mid,'rating':'down'}).status_code,400)
        self.assertEqual(self.client.post('/admin/feedback',json={'session_id':'test-session','message_id':mid,'rating':'down','comment':'回复太长'}).status_code,200)
        self.client.post('/admin/feedback',json={'session_id':'test-session','message_id':mid,'rating':'up'})
        with self.sessions() as db: self.assertEqual(db.query(Feedback).count(),1)

    def test_resume_from_sequence_without_duplicate(self):
        response,_=self.chat()
        resumed=self.client.post('/chat',json={'session_id':'test-session','request_id':'request-1','message':'你好','after_seq':2})
        self.assertNotIn('id: 1\n',resumed.text)
        self.assertIn('event: done',resumed.text)

    def test_sample_edit_returns_to_review_and_warning_ack(self):
        sample=self.client.post('/admin/training-samples',json={'question':'价格','answer':'价格8888元','reason':'直接报','source':'用户标注'}).json()
        self.assertEqual(self.client.patch(f"/admin/training-samples/{sample['id']}?status=approved").status_code,409)
        self.client.patch(f"/admin/training-samples/{sample['id']}?status=approved&acknowledge=true")
        self.client.put(f"/admin/training-samples/{sample['id']}",json={'question':'价格','answer':'先问意向','reason':'规则'})
        with self.sessions() as db: self.assertEqual(db.get(TrainingSample,sample['id']).status,'pending')

    def test_knowledge_index_approval_edit_and_withdraw(self):
        row=self.client.post('/admin/knowledge',json={'question':'Python 入门基础','answer':'Python 入门基础先理解变量和循环','source':'人工教研确认'}).json()
        self.assertFalse(search_knowledge('Python 入门基础')['matches'])
        self.client.patch(f"/admin/knowledge/{row['id']}?status=approved")
        hit=search_knowledge('Python 入门基础')['matches'][0]
        self.assertEqual(hit['source'],'人工教研确认')
        self.client.put(f"/admin/knowledge/{row['id']}",json={'question':'新知识','answer':'新内容','source':'人工确认'})
        with self.sessions() as db: self.assertIsNone(db.get(KnowledgeVector,row['id']))
        self.assertFalse(search_knowledge('Python 入门基础')['matches'])

    def test_order_is_session_bound_and_cases_not_invented(self):
        self.assertFalse(build_registry('other').call('order_query',{'order_id':'DEMO-001'})['found'])
        self.assertTrue(build_registry('demo-session').call('order_query',{'order_id':'DEMO-001'})['demo'])
        self.assertEqual(build_registry().call('student_cases',{'city':'上海'})['matches'],[])

    def test_low_confidence_creates_ticket(self):
        result=build_registry('test-session').call('assess_confidence',{'confidence':.2,'reason':'事实缺失'})
        self.assertIn('ticket_id',result['handoff'])

    def test_tool_schema_validation(self):
        with self.assertRaises(ValueError): build_registry().call('student_cases',{})
        with self.assertRaises(ValueError): build_registry('s').call('assess_confidence',{'confidence':2,'reason':'错误'})

    def test_global_stream_guard_split_price_and_three_sentences(self):
        guard=StreamingGuard(sentence_policy)
        text=''.join(guard.feed(c) for c in '费用是8888元。赶紧报名。第三句。第四句。')+guard.finish()
        self.assertNotIn('8888',text);self.assertNotIn('赶紧报名',text);self.assertNotIn('第四句',text)
        self.assertLessEqual(sum(text.count(c) for c in '。！？!?'),3)
        for raw in ('￥9800','八千元','价格为9800','100%保证就业。'):
            self.assertNotEqual(sentence_policy(raw),raw)

    def test_optimizer_uses_feedback_generates_actual_diff_and_deduplicates(self):
        from agent.optimizer import generate_proposal
        _,rows=self.chat()
        self.client.post('/admin/feedback',json={'session_id':'test-session','message_id':rows[-1]['message_id'],'rating':'down','comment':'回复太长'})
        result=generate_proposal(FakeClient())
        self.assertEqual(result['status'],'pending')
        history=self.client.get('/admin/prompts').json()['proposals'][0]
        self.assertTrue(history['diff'].startswith('---'))
        self.assertIn('回复太长',history['rationale'])
        self.assertEqual(generate_proposal(FakeClient())['status'],'skipped')

    def test_auto_optimize_threshold(self):
        _,rows=self.chat()
        with patch.dict(os.environ,{'OPTIMIZE_THRESHOLD':'1'}),patch('api.admin.generate_proposal',return_value={'status':'pending'}) as generate:
            self.client.post('/admin/feedback',json={'session_id':'test-session','message_id':rows[-1]['message_id'],'rating':'down'})
            generate.assert_called_once()

    def test_proposal_publish_checks_base_and_runs_same_smoke(self):
        from agent.optimizer import generate_proposal
        _,rows=self.chat()
        self.client.post('/admin/feedback',json={'session_id':'test-session','message_id':rows[-1]['message_id'],'rating':'down'})
        proposal=generate_proposal(FakeClient())
        with patch('api.admin.model_smoke_tests',return_value={'passed':True,'mode':'test_stub','results':[]}) as smoke:
            result=self.client.post(f"/admin/prompts/proposals/{proposal['id']}/approve")
            self.assertEqual(result.status_code,200);smoke.assert_called_once()
            self.assertEqual(self.client.post(f"/admin/prompts/proposals/{proposal['id']}/approve").status_code,409)

    def test_replay_is_read_only(self):
        self.chat('模型转人工')
        run=self.client.get('/admin/runs').json()[0]
        count=len(self.client.get('/admin/tickets').json())
        result=self.client.post('/admin/replays',json={'run_id':run['id'],'prompt_version':0,'knowledge_mode':'snapshot'})
        self.assertEqual(result.status_code,200)
        self.assertEqual(len(self.client.get('/admin/tickets').json()),count)
        self.assertEqual(len(self.client.get('/admin/replays').json()),1)

    def test_cancel_request_and_recover_restart(self):
        import time
        from agent.jobs import start_request, recover_interrupted
        class SlowClient(FakeClient):
            def stream(self,messages,tools=None):
                for _ in range(20):
                    time.sleep(.05)
                    yield Obj(choices=[Obj(delta=Obj(content='继续',tool_calls=[]))])
        with patch('agent.runtime.QwenClient',SlowClient):
            key=start_request('cancel-session','cancel-id','测试取消')
            self.client.post('/chat/cancel',json={'session_id':'cancel-session','request_id':'cancel-id'})
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                with self.sessions() as db:
                    if db.get(ChatRun,key).status!='running': break
                time.sleep(.05)
            with self.sessions() as db: self.assertEqual(db.get(ChatRun,key).status,'cancelled')
        with self.sessions() as db:
            db.add(ChatRun(id='abandoned',session_id='s',request_id='restart',question='旧问题',status='running'))
            db.commit()
        recover_interrupted()
        with self.sessions() as db:
            row=db.get(ChatRun,'abandoned'); self.assertEqual(row.status,'interrupted'); self.assertIn('done',row.events)

    def test_heartbeat_while_model_has_no_output(self):
        import time
        class WaitingClient(FakeClient):
            def stream(self,messages,tools=None):
                time.sleep(5.4)
                yield Obj(choices=[Obj(delta=Obj(content='完成。',tool_calls=[]))])
        with patch('agent.runtime.QwenClient',WaitingClient):
            response,_=self.chat()
        self.assertIn(': heartbeat',response.text)

    def test_context_compaction_keeps_coherent_groups(self):
        from harness.context import compact_history
        history=[{'role':'user','content':'早期问题'*200},{'role':'assistant','content':'早期回答'*200},{'role':'user','content':'最近问题'},{'role':'assistant','content':'最近回答'}]
        kept,summary=compact_history(history,max_chars=100)
        self.assertEqual([m['content'] for m in kept],['最近问题','最近回答'])
        self.assertIn('早期问题',summary)

    def test_turn_profile_uses_user_facts_not_assistant_assertions(self):
        loop=ConsultantLoop(client=FakeClient(),session_id='test-session',history=[{'role':'assistant','content':'你是不是在北京？'}])
        list(loop.run_with_tools('我在上海，认真转行。'))
        result=loop.registry.call('handoff',{'reason':'客户请求','summary':'转班主任'})
        self.assertEqual(result['student_profile']['city'],'上海')

if __name__=='__main__': unittest.main()
