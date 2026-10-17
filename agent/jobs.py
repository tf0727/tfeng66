"""Persistent chat requests, resumable event journal and bounded background execution."""
import json
import logging
from threading import RLock, Thread
from time import perf_counter
from uuid import uuid4
from datetime import datetime, timezone

from db.models import ChatRun, Message, Session, SessionLocal
from agent.runtime import ConsultantLoop
from agent.prompt_store import active_prompt_state
from agent.samples import approved_samples
from agent.knowledge import knowledge_snapshot
from agent.handoff import should_handoff, build_profile, summarize
from agent.ticket_store import create_ticket
from harness.context import compact_history

logger=logging.getLogger('consultant.requests')
LOCK=RLock()

def run_key(session_id,request_id): return json.dumps([session_id,request_id],ensure_ascii=False,separators=(',',':'))

def append_event(key,kind,data):
    with SessionLocal() as db:
        row=db.get(ChatRun,key)
        events=json.loads(row.events)
        item={'event':kind,'data':{**data,'trace_id':row.request_id,'timestamp':datetime.now(timezone.utc).isoformat()},'seq':len(events)+1}
        events.append(item); row.events=json.dumps(events,ensure_ascii=False); db.commit()
    # Log metadata only, never raw question, arguments, API key or model output.
    logger.info(json.dumps({'request_id':row.request_id,'event':kind,'seq':item['seq'],'stage':data.get('stage'),'status':data.get('status')},ensure_ascii=False))

def execute(key):
    started=perf_counter(); answer=[]; mode='model'; terminal='completed'; prompt_version=0
    def emit(kind,data): append_event(key,kind,data)
    def cancelled():
        with SessionLocal() as db: return bool(db.get(ChatRun,key).cancel)
    try:
        with SessionLocal() as db:
            run=db.get(ChatRun,key); session_id,question,request_id=run.session_id,run.question,run.request_id
            rows=db.query(Message).filter(Message.session_id==session_id,Message.request_id!=request_id).order_by(Message.id).all()
            history=[{'role':r.role,'content':r.content} for r in rows]
        state=active_prompt_state(); prompt_version=state['version']; samples=approved_samples(); knowledge=knowledge_snapshot()
        loop=ConsultantLoop(system_prompt=state['content'],prompt_version=prompt_version,session_id=session_id,history=history,knowledge=knowledge,samples=samples,cancelled=cancelled)
        loop.prepare_context()
        with SessionLocal() as db:
            run=db.get(ChatRun,key); run.prompt_version=prompt_version; run.prompt_snapshot=loop.messages[0]['content']; run.knowledge_snapshot=json.dumps(knowledge,ensure_ascii=False)
            session=db.get(Session,session_id); session.profile=json.dumps(build_profile('\n'.join(m['content'] for m in history if m['role']=='user')+'\n'+question),ensure_ascii=False)
            _, session.summary=compact_history(history)
            db.commit()
        emit('trace',{'stage':'received','summary':'请求已登记；恢复数据库历史并冻结本轮 Prompt 和知识快照。','prompt_version':prompt_version})
        need,reason=should_handoff(question)
        if need or not samples:
            cid='preflight-'+uuid4().hex
            emit('tool_start',{'call_id':cid,'name':'recall_playbook','arguments':{},'summary':'每轮强制取回全部审核样本。'})
            emit('tool_end',{'call_id':cid,'name':'recall_playbook','result':samples,'status':'success','elapsed_ms':0})
            cause=reason if need else 'empty_playbook'
            cid=uuid4().hex
            args={'reason':cause,'summary':summarize(question),'student_profile':build_profile('\n'.join(m['content'] for m in history if m['role']=='user')+'\n'+question)}
            emit('tool_start',{'call_id':cid,'name':'handoff','arguments':args})
            ticket=create_ticket(session_id,**args)
            emit('tool_end',{'call_id':cid,'name':'handoff','result':ticket,'status':'success','elapsed_ms':0})
            emit('handoff',ticket)
            events=[{'type':'delta','content':f"已整理您的情况并转交班主任，工单号为 {ticket['ticket_id']}。请等待进一步确认。"}]
            mode='handoff'
        else:
            events=loop.run_with_tools(question,prepared=True)
        for item in events:
            if cancelled(): raise InterruptedError()
            data=dict(item); kind=data.pop('type')
            if kind=='delta' and data.get('content'):
                if not answer:
                    with SessionLocal() as db:
                        db.get(ChatRun,key).first_token_ms=round((perf_counter()-started)*1000); db.commit()
                answer.append(data['content'])
            emit(kind,data)
            if kind=='tool_end':
                result=data.get('result',{})
                ticket=result.get('handoff') if isinstance(result,dict) else None
                if data.get('name')=='handoff' and isinstance(result,dict): ticket=result
                if ticket and ticket.get('ticket_id'):
                    emit('handoff',ticket); mode='handoff'
        if not answer:
            text='本轮未生成有效回复，您可以补充学习目标，或让班主任帮助确认。'
            answer.append(text); emit('delta',{'content':text})
    except InterruptedError:
        mode='cancelled'; terminal='cancelled'; emit('trace',{'stage':'cancelled','summary':'已停止生成，已输出部分保留。'})
    except Exception as exc:
        mode='fallback'
        emit('trace',{'stage':'fallback','status':'error','summary':'模型服务或工具执行失败，当前为演示兜底，不计入真实模型成功。','error_type':type(exc).__name__})
        text='服务暂时不可用。您可以稍后重试，或告诉我希望转行还是提升。'
        if not answer: answer.append(text); emit('delta',{'content':text})
        emit('error',{'message':'模型调用失败，已标记演示兜底。','error_type':type(exc).__name__})
    finally:
        elapsed=round((perf_counter()-started)*1000)
        with SessionLocal() as db:
            run=db.get(ChatRun,key); run.reply=''.join(answer); run.mode=mode; run.elapsed_ms=elapsed
            message=Message(session_id=run.session_id,role='assistant',content=run.reply,request_id=run.request_id,prompt_version=prompt_version)
            db.add(message); db.commit(); message_id=message.id
        emit('done',{'elapsed_ms':elapsed,'message_id':message_id,'prompt_version':prompt_version,'mode':mode,'status':terminal})
        with SessionLocal() as db: db.get(ChatRun,key).status=terminal; db.commit()

def start_request(session_id,request_id,question):
    key=run_key(session_id,request_id)
    with LOCK,SessionLocal() as db:
        existing=db.get(ChatRun,key)
        if existing:
            if existing.question!=question: raise ValueError('同一 request_id 不得提交不同问题')
            return key
        if db.query(ChatRun).filter_by(session_id=session_id,status='running').first(): raise RuntimeError('该会话已有生成中的请求')
        if not db.get(Session,session_id): db.add(Session(id=session_id))
        db.add(ChatRun(id=key,session_id=session_id,request_id=request_id,question=question))
        db.add(Message(session_id=session_id,role='user',content=question,request_id=request_id))
        db.commit()
        append_event(key,'start',{'session_id':session_id,'request_id':request_id})
        Thread(target=execute,args=(key,),daemon=True,name='chat-'+request_id[:8]).start()
    return key

def recover_interrupted():
    with SessionLocal() as db:
        rows=db.query(ChatRun).filter_by(status='running').all()
        for row in rows:
            events=json.loads(row.events)
            for kind,data in [('error',{'message':'服务重启中断本请求，请使用新请求重试。'}),('done',{'mode':'interrupted','status':'interrupted'})]:
                events.append({'seq':len(events)+1,'event':kind,'data':{**data,'trace_id':row.request_id,'timestamp':datetime.now(timezone.utc).isoformat()}})
            row.events=json.dumps(events,ensure_ascii=False); row.status='interrupted'; row.mode='interrupted'
        db.commit()
