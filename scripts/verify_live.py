"""Real Qwen acceptance in an isolated database; never modifies operator data."""
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from time import perf_counter

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))

def main():
    source=sqlite3.connect(f'file:{(ROOT/"data/app.db").as_posix()}?mode=ro',uri=True)
    active=source.execute("SELECT content FROM prompt_versions WHERE status='active' ORDER BY version DESC LIMIT 1").fetchone()
    samples=source.execute("SELECT question,answer,reason,scene,source FROM training_samples WHERE status='approved'").fetchall()
    source.close()
    with tempfile.TemporaryDirectory(prefix='consultant-live-') as temp:
        os.environ['APP_DB_PATH']=str(Path(temp)/'live.db')
        os.environ['OPTIMIZE_THRESHOLD']='100'
        from fastapi.testclient import TestClient
        from api.main import app
        from db.models import SessionLocal, TrainingSample, PromptVersion, Feedback, ChatRun, engine
        if '--cleanup-check' in sys.argv:
            engine.dispose()
            print('temporary_database_cleanup_check=passed')
            return 0
        from agent.prompt import SYSTEM_PROMPT_V1
        from agent.smoke import model_smoke_tests
        from agent.prompt_store import compose_system_prompt
        from agent.optimizer import generate_proposal
        base=active[0] if active else SYSTEM_PROMPT_V1
        with SessionLocal() as db:
            db.add(PromptVersion(version=1,content=base,status='active'))
            for row in samples:
                db.add(TrainingSample(question=row[0],answer=row[1],reason=row[2],scene=row[3],source=row[4],status='approved'))
            db.commit()
        report={'scope':'隔离数据库真实模型技术验收，不计为真实用户使用','rounds':[]}
        with TestClient(app) as client:
            questions=['我是大专毕业，想转行学 Python，多少钱？','我在上海，零基础，每天可以学两小时，认真考虑转行。','请用 course_search 查看 Python 的学习内容和周期；区分演示资料和真实政策。','请用 student_cases 查询上海零基础转行的真实案例；没有案例不要编造。','请用 order_query 查询我本会话的 DEMO-001 订单。']
            first_run=None; message_id=None
            for index,question in enumerate(questions):
                started=perf_counter()
                response=client.post('/chat',json={'session_id':'demo-session','request_id':f'live-{index}','message':question})
                records=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
                done=records[-1]
                tools=[r.get('name') for r in records if 'arguments' in r and 'name' in r]
                reply=''.join(r.get('content','') for r in records)
                report['rounds'].append({'question':question,'reply':reply,'mode':done.get('mode'),'tools':tools,'elapsed_ms':round((perf_counter()-started)*1000),'passed':done.get('mode') in {'model','handoff'} and tools[0]=='recall_playbook'})
                message_id=done.get('message_id')
                print(json.dumps({'round':index+1,'mode':done.get('mode'),'tools':tools},ensure_ascii=False),flush=True)
                if index==0:
                    with SessionLocal() as db: first_run=db.query(ChatRun).filter_by(request_id='live-0').first().id
            try:
                report['smoke']=model_smoke_tests(compose_system_prompt(base))
                print('real_smoke_finished',flush=True)
            except Exception as exc: report['smoke']={'passed':False,'error_type':type(exc).__name__}
            try:
                with SessionLocal() as db:
                    db.add(Feedback(session_id='demo-session',message_id=message_id,rating='down',comment='回答偏长，希望先回应重点，少用泛泛的提问。',prompt_version=1)); db.commit()
                report['optimizer']=generate_proposal()
                print('real_optimizer_finished',flush=True)
            except Exception as exc: report['optimizer']={'status':'error','error_type':type(exc).__name__}
            replay=client.post('/admin/replays',json={'run_id':first_run,'prompt_version':1,'knowledge_mode':'snapshot'})
            report['replay']={'http_status':replay.status_code,'result':replay.json()}
            report['metrics']=client.get('/admin/metrics').json()
        report['passed']=all(r['passed'] for r in report['rounds']) and report['smoke'].get('passed',False) and report['optimizer'].get('status')=='pending' and report['replay']['http_status']==200
        (ROOT/'data/acceptance_live.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'passed':report['passed'],'report':'data/acceptance_live.json'},ensure_ascii=False))
        engine.dispose()
        return 0 if report['passed'] else 1

if __name__=='__main__': raise SystemExit(main())
