import difflib
import json
import logging
import os
from datetime import datetime, timezone
from threading import RLock

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field
from db.models import (Feedback, PromptProposal, PromptVersion, SessionLocal, Ticket, TrainingSample,
                       Message, AuditEvent, KnowledgeEntry, ChatRun, Replay)
from agent.prompt import SYSTEM_PROMPT_V1
from agent.optimizer import generate_proposal
from agent.smoke import run_smoke_tests, model_smoke_tests
from agent.prompt_store import compose_system_prompt
from agent.sample_prompt import build_training_system_prompt
from agent.samples import approved_samples
from agent.output_guard import PRICE
from agent.ticket_store import create_ticket
from agent.knowledge import index_entry, knowledge_snapshot
from agent.runtime import ConsultantLoop

router=APIRouter(prefix='/admin')
PROMPT_LOCK=RLock()
logger=logging.getLogger('consultant.admin')

def record(db,kind,target,detail=None,actor='本地管理员'):
    db.add(AuditEvent(kind=kind,target=str(target),actor=actor,detail=json.dumps(detail or {},ensure_ascii=False)))

def sample_warnings(answer,reason=''):
    warnings=[]
    if PRICE.search(answer): warnings.append('答案含具体价格，与不报价铁律冲突')
    if '骗子' in answer: warnings.append('包含对他人的绝对化定性，建议改成客观政策说明')
    if not reason.strip(): warnings.append('未填写回答原因')
    return warnings

class TrainingSampleRequest(BaseModel):
    question:str=Field(min_length=1,max_length=5000)
    answer:str=Field(min_length=1,max_length=10000)
    reason:str=''
    scene:str='通用'
    source:str='人工录入'

def sample_dict(row):
    return {**{k:getattr(row,k) for k in ('id','question','answer','reason','scene','status','source','reviewer','reviewed_at','review_note')},'warnings':sample_warnings(row.answer,row.reason)}

@router.get('/training-samples')
def list_training_samples():
    with SessionLocal() as db: return [sample_dict(r) for r in db.query(TrainingSample).order_by(TrainingSample.id.desc()).all()]

@router.post('/training-samples')
def add_training_sample(body:TrainingSampleRequest):
    if not body.question.strip() or not body.answer.strip(): raise HTTPException(400,'问题和答案不能为空')
    with SessionLocal() as db:
        row=TrainingSample(**body.model_dump(),status='pending'); db.add(row); db.flush(); record(db,'sample_create',row.id); db.commit()
        return sample_dict(row)

@router.put('/training-samples/{sample_id}')
def edit_training_sample(sample_id:int,body:TrainingSampleRequest):
    with SessionLocal() as db:
        row=db.get(TrainingSample,sample_id)
        if not row: raise HTTPException(404,'样本不存在')
        record(db,'sample_edit',sample_id,{'before':sample_dict(row),'after':body.model_dump()})
        for key,value in body.model_dump().items(): setattr(row,key,value)
        row.status='pending'; row.reviewer=''; row.reviewed_at=''; row.review_note=''
        db.commit(); return sample_dict(row)

@router.patch('/training-samples/{sample_id}')
def review_training_sample(sample_id:int,status:str,reviewer:str='本地管理员',note:str='',acknowledge:bool=False):
    if status not in {'pending','approved','rejected'}: raise HTTPException(400,'非法状态')
    with SessionLocal() as db:
        row=db.get(TrainingSample,sample_id)
        if not row: raise HTTPException(404,'样本不存在')
        warnings=sample_warnings(row.answer,row.reason)
        if status=='approved' and warnings and not acknowledge: raise HTTPException(409,{'warnings':warnings,'message':'请修订内容或显式确认冲突；运行时铁律仍然优先。'})
        row.status=status; row.reviewer=reviewer; row.reviewed_at=datetime.now(timezone.utc).isoformat(); row.review_note=note
        record(db,'sample_review',sample_id,{'status':status,'note':note,'warnings':warnings},reviewer); db.commit(); return sample_dict(row)

@router.delete('/training-samples/{sample_id}')
def delete_training_sample(sample_id:int):
    with SessionLocal() as db:
        row=db.get(TrainingSample,sample_id)
        if not row: raise HTTPException(404,'样本不存在')
        record(db,'sample_delete',sample_id,sample_dict(row)); db.delete(row); db.commit()
    return {'status':'deleted'}

class PlaybookRequest(BaseModel):
    scene:str
    sample:str
    keywords:list[str]=[]
    question:str='此场景的示范咨询'
    reason:str=''

@router.get('/playbook')
def list_playbook():
    return [{'id':str(r['id']),'scene':r['scene'],'keywords':[],'sample':r['answer'],'question':r['question'],'reason':r['reason']} for r in approved_samples()]

@router.post('/playbook')
def add_playbook(body:PlaybookRequest):
    return add_training_sample(TrainingSampleRequest(question=body.question,answer=body.sample,reason=body.reason,scene=body.scene,source='套路库人工教学'))

@router.put('/playbook/{sample_id}')
def edit_playbook(sample_id:int,body:PlaybookRequest):
    return edit_training_sample(sample_id,TrainingSampleRequest(question=body.question,answer=body.sample,reason=body.reason,scene=body.scene,source='套路库人工教学'))

@router.delete('/playbook/{sample_id}')
def delete_playbook(sample_id:int): return delete_training_sample(sample_id)

class HandoffRequest(BaseModel):
    session_id:str
    reason:str
    summary:str
    student_profile:dict=Field(default_factory=dict)
    confidence:float | None=Field(default=None,ge=0,le=1)

@router.post('/handoff')
def create_handoff(body:HandoffRequest): return create_ticket(**body.model_dump())

@router.get('/tickets')
def list_tickets():
    with SessionLocal() as db:
        return [{**{k:getattr(r,k) for k in ('id','session_id','reason','summary','status','confidence','created_at')},'student_profile':json.loads(r.profile)} for r in db.query(Ticket).order_by(Ticket.created_at.desc()).all()]

@router.patch('/tickets/{ticket_id}')
def update_ticket(ticket_id:str,status:str):
    allowed={'queued':{'assigned'},'assigned':{'resolved'},'resolved':set()}
    with SessionLocal() as db:
        row=db.get(Ticket,ticket_id)
        if not row: raise HTTPException(404,'工单不存在')
        if status!=row.status and status not in allowed[row.status]: raise HTTPException(400,'必须依次 queued → assigned → resolved')
        row.status=status; record(db,'ticket_status',ticket_id,{'status':status}); db.commit()
    return {'id':ticket_id,'status':status}

class FeedbackRequest(BaseModel):
    session_id:str
    message_id:int
    rating:str
    comment:str=''

def optimize_background():
    try: generate_proposal()
    except Exception as exc:
        logger.warning('optimizer_failed type=%s',type(exc).__name__)
        with SessionLocal() as db: record(db,'optimizer_failed','background',{'error_type':type(exc).__name__}); db.commit()

@router.post('/feedback')
def create_feedback(body:FeedbackRequest,background:BackgroundTasks):
    if body.rating not in {'up','down'}: raise HTTPException(400,'非法评价')
    with SessionLocal() as db:
        message=db.get(Message,body.message_id)
        if not message or message.role!='assistant' or message.session_id!=body.session_id: raise HTTPException(400,'回复与会话不匹配')
        row=db.query(Feedback).filter_by(session_id=body.session_id,message_id=body.message_id).first()
        if not row:
            row=Feedback(session_id=body.session_id,message_id=body.message_id); db.add(row)
        row.rating=body.rating; row.comment=body.comment; row.prompt_version=message.prompt_version; db.commit()
        pending=db.query(Feedback).filter(Feedback.rating=='down',Feedback.proposal_id.is_(None),Feedback.message_id.is_not(None)).count()
        threshold=max(1,int(os.getenv('OPTIMIZE_THRESHOLD','3')))
        if pending>=threshold: background.add_task(optimize_background)
        return {'id':row.id,'status':'recorded','prompt_version':row.prompt_version,'optimization_queued':pending>=threshold}

class PromptRequest(BaseModel):
    content:str=Field(min_length=1,max_length=60000)
    base_version:int | None=None

def active(db):
    return db.query(PromptVersion).filter_by(status='active').order_by(PromptVersion.version.desc()).first()

def validated(content):
    errors=run_smoke_tests(content)
    if errors: raise HTTPException(400,errors)
    try: result=model_smoke_tests(compose_system_prompt(content))
    except Exception as exc: raise HTTPException(503,{'message':'真实模型冒烟测试不可用，未发布','error_type':type(exc).__name__})
    if not result['passed']: raise HTTPException(400,{'message':'真实模型红线测试未通过，未发布','report':result})
    return result

@router.get('/prompts')
def list_prompts():
    with SessionLocal() as db:
        versions=db.query(PromptVersion).order_by(PromptVersion.version.desc()).all()
        proposals=db.query(PromptProposal).order_by(PromptProposal.id.desc()).all()
        return {'versions':[{k:getattr(r,k) for k in ('version','status','content')} for r in versions],
                'proposals':[{k:getattr(r,k) for k in ('id','base_version','diff','status','candidate','rationale','feedback_ids')} for r in proposals]}

@router.get('/prompts/context')
def prompt_context():
    with SessionLocal() as db:
        row=active(db); base=row.content if row else SYSTEM_PROMPT_V1; version=row.version if row else 0
    samples=approved_samples()
    return {'version':version,'content':base,'training_prompt':build_training_system_prompt(samples),'full_prompt':compose_system_prompt(base,samples),'approved_samples':len(samples)}

@router.post('/prompts/preview')
def preview_prompt(body:PromptRequest): return {'full_prompt':compose_system_prompt(body.content)}

@router.post('/prompts/smoke')
def smoke_prompt(body:PromptRequest): return validated(body.content)

@router.post('/prompts')
def save_prompt(body:PromptRequest):
    with PROMPT_LOCK:
        with SessionLocal() as db:
            row=active(db); base_version=row.version if row else 0
            if body.base_version is not None and base_version!=body.base_version: raise HTTPException(409,'基准版本已变化，请刷新')
        report=validated(body.content)
        with SessionLocal() as db:
            row=active(db)
            if (row.version if row else 0)!=base_version: raise HTTPException(409,'测试期间基准版本变化，请重试')
            latest=db.query(PromptVersion).order_by(PromptVersion.version.desc()).first(); version=latest.version+1 if latest else 1
            db.query(PromptVersion).update({'status':'archived'})
            db.add(PromptVersion(version=version,content=body.content,status='active'))
            record(db,'prompt_publish',version,{'smoke':report}); db.commit()
    return {'version':version,'status':'active','smoke':report}

@router.post('/prompts/{version}/rollback')
def rollback_prompt(version:int):
    with PROMPT_LOCK:
        with SessionLocal() as db:
            target=db.query(PromptVersion).filter_by(version=version).first()
            if not target: raise HTTPException(404,'版本不存在')
            content=target.content
        report=validated(content)
        with SessionLocal() as db:
            db.query(PromptVersion).update({'status':'archived'})
            db.query(PromptVersion).filter_by(version=version).update({'status':'active'})
            record(db,'prompt_rollback',version,{'smoke':report}); db.commit()
    return {'version':version,'status':'active'}

class ProposalRequest(BaseModel):
    base_version:int
    diff:str
    candidate:str=''
    rationale:str='人工建议'

@router.post('/prompts/proposals')
def create_proposal(body:ProposalRequest):
    candidate=body.candidate or body.diff
    errors=run_smoke_tests(candidate)
    if errors: raise HTTPException(400,errors)
    with SessionLocal() as db:
        row=active(db)
        if (row.version if row else 0)!=body.base_version: raise HTTPException(409,'建议基准已过期')
        base=row.content if row else SYSTEM_PROMPT_V1
        diff=''.join(difflib.unified_diff(base.splitlines(True),candidate.splitlines(True),fromfile=f'v{body.base_version}',tofile='candidate'))
        proposal=PromptProposal(base_version=body.base_version,candidate=candidate,diff=diff,rationale=body.rationale)
        db.add(proposal); db.commit()
        return {'id':proposal.id,'status':proposal.status}

@router.post('/prompts/proposals/{proposal_id}/approve')
def approve_proposal(proposal_id:int):
    with PROMPT_LOCK:
        with SessionLocal() as db:
            row=db.get(PromptProposal,proposal_id)
            if not row: raise HTTPException(404,'建议不存在')
            if row.status!='pending': raise HTTPException(409,'建议已处理')
            if not row.candidate: raise HTTPException(400,'旧建议缺少独立候选 Prompt，请在编辑器重新生成')
            content=row.candidate; base_version=row.base_version
        result=save_prompt(PromptRequest(content=content,base_version=base_version))
        with SessionLocal() as db:
            row=db.get(PromptProposal,proposal_id); row.status='approved'; record(db,'proposal_approve',proposal_id,{'version':result['version']}); db.commit()
        return {'proposal_id':proposal_id,**result}

@router.post('/prompts/proposals/{proposal_id}/reject')
def reject_proposal(proposal_id:int):
    with PROMPT_LOCK, SessionLocal() as db:
        row=db.get(PromptProposal,proposal_id)
        if not row: raise HTTPException(404,'建议不存在')
        if row.status!='pending': raise HTTPException(409,'建议已处理')
        row.status='rejected'; record(db,'proposal_reject',proposal_id); db.commit()
    return {'status':'rejected'}

@router.post('/prompts/optimize')
def optimize_prompt():
    try: return generate_proposal()
    except Exception as exc: raise HTTPException(503,{'message':'模型优化失败，未创建虚假建议','error_type':type(exc).__name__})

class KnowledgeRequest(BaseModel):
    question:str=Field(min_length=1)
    answer:str=Field(min_length=1)
    source:str=Field(min_length=1)

@router.get('/knowledge')
def list_knowledge():
    with SessionLocal() as db:
        return [{k:getattr(r,k) for k in ('id','question','answer','source','status','version','reviewer','reviewed_at','review_note')} for r in db.query(KnowledgeEntry).order_by(KnowledgeEntry.id.desc()).all()]

@router.post('/knowledge')
def create_knowledge(body:KnowledgeRequest):
    with SessionLocal() as db:
        row=KnowledgeEntry(**body.model_dump()); db.add(row); db.flush(); record(db,'knowledge_create',row.id); db.commit()
        return {'id':row.id,'status':row.status}

@router.put('/knowledge/{entry_id}')
def edit_knowledge(entry_id:int,body:KnowledgeRequest):
    with SessionLocal() as db:
        row=db.get(KnowledgeEntry,entry_id)
        if not row: raise HTTPException(404,'知识不存在')
        record(db,'knowledge_edit',entry_id,{'previous':{k:getattr(row,k) for k in ('question','answer','source','version')}})
        for k,v in body.model_dump().items(): setattr(row,k,v)
        row.version+=1; row.status='pending'; row.reviewer=''; row.reviewed_at=''; index_entry(db,row); db.commit()
    return {'id':entry_id,'status':'pending'}

@router.patch('/knowledge/{entry_id}')
def review_knowledge(entry_id:int,status:str,reviewer:str='本地管理员',note:str=''):
    if status not in {'approved','rejected'}: raise HTTPException(400,'非法审核状态')
    with SessionLocal() as db:
        row=db.get(KnowledgeEntry,entry_id)
        if not row: raise HTTPException(404,'知识不存在')
        row.status=status; row.reviewer=reviewer; row.reviewed_at=datetime.now(timezone.utc).isoformat(); row.review_note=note
        index_entry(db,row); record(db,'knowledge_review',entry_id,{'status':status,'version':row.version},reviewer); db.commit()
    return {'status':status,'indexed':status=='approved'}

@router.delete('/knowledge/{entry_id}')
def delete_knowledge(entry_id:int):
    with SessionLocal() as db:
        row=db.get(KnowledgeEntry,entry_id)
        if not row: raise HTTPException(404,'知识不存在')
        row.status='rejected'; index_entry(db,row); record(db,'knowledge_archive',entry_id); db.commit()
    return {'status':'archived'}

@router.get('/runs')
def list_runs():
    with SessionLocal() as db:
        return [{k:getattr(r,k) for k in ('id','request_id','session_id','question','reply','status','mode','prompt_version','first_token_ms','elapsed_ms','created_at')} for r in db.query(ChatRun).order_by(ChatRun.created_at.desc()).limit(100).all()]

class ReplayRequest(BaseModel):
    run_id:str
    prompt_version:int
    knowledge_mode:str='snapshot'

@router.post('/replays')
def create_replay(body:ReplayRequest):
    if body.knowledge_mode not in {'snapshot','current'}: raise HTTPException(400,'非法知识版本选择')
    with SessionLocal() as db:
        run=db.get(ChatRun,body.run_id)
        if not run or not run.prompt_snapshot: raise HTTPException(404,'原请求或快照不存在')
        prompt=db.query(PromptVersion).filter_by(version=body.prompt_version).first()
        if not prompt and body.prompt_version!=0: raise HTTPException(404,'Prompt 版本不存在')
        base=prompt.content if prompt else SYSTEM_PROMPT_V1
        events=json.loads(run.events)
        original_samples=next((e['data']['result'] for e in events if e['event']=='tool_end' and e['data'].get('name')=='recall_playbook' and isinstance(e['data'].get('result'),list)),[])
        samples=original_samples if body.knowledge_mode=='snapshot' else approved_samples()
        knowledge=json.loads(run.knowledge_snapshot) if body.knowledge_mode=='snapshot' else knowledge_snapshot()
        history_rows=db.query(Message).filter(Message.session_id==run.session_id,Message.role=='user',Message.request_id==run.request_id).first()
        history=[{'role':m.role,'content':m.content} for m in db.query(Message).filter(Message.session_id==run.session_id,Message.id<(history_rows.id if history_rows else 0)).order_by(Message.id).all()]
        question=run.question; original=run.reply; original_system=run.prompt_snapshot; original_version=run.prompt_version; replay_session=run.session_id
    try:
        loop=ConsultantLoop(system_prompt=base,prompt_version=body.prompt_version,session_id=replay_session,history=history,knowledge=knowledge,samples=samples,read_only=True)
        loop.prepare_context()
        if body.knowledge_mode=='snapshot' and body.prompt_version==original_version:
            loop.messages[0]['content']=original_system
        trace=list(loop.run_with_tools(question,prepared=True))
    except Exception as exc: raise HTTPException(503,{'message':'回放模型不可用，未保存虚假对比','error_type':type(exc).__name__})
    reply=''.join(e['content'] for e in trace if e['type']=='delta')
    with SessionLocal() as db:
        row=Replay(run_id=body.run_id,question=question,prompt_version=body.prompt_version,knowledge_mode=body.knowledge_mode,knowledge_snapshot=json.dumps(knowledge,ensure_ascii=False),reply=reply,trace=json.dumps(trace,ensure_ascii=False))
        db.add(row); db.commit()
        return {'id':row.id,'question':question,'original':original,'reply':reply,'diff':'\n'.join(difflib.unified_diff(original.splitlines(),reply.splitlines(),fromfile='original',tofile='replay')),'trace':trace}

@router.get('/replays')
def list_replays():
    with SessionLocal() as db:
        return [{k:getattr(r,k) for k in ('id','run_id','question','prompt_version','knowledge_mode','reply','created_at')} for r in db.query(Replay).order_by(Replay.id.desc()).limit(100).all()]

@router.get('/metrics')
def metrics():
    with SessionLocal() as db:
        rows=db.query(ChatRun).all()
        latencies=sorted(r.first_token_ms for r in rows if r.first_token_ms is not None and r.mode=='model')
        modes={mode:sum(r.mode==mode for r in rows) for mode in ('model','fallback','handoff','cancelled','interrupted')}
        tickets=db.query(Ticket).all()
        return {'scope':'本地技术运行记录，非业务效果评估','requests':len(rows),'modes':modes,'real_model_first_sentence_ms':{'count':len(latencies),'median':latencies[len(latencies)//2] if latencies else None,'max':max(latencies) if latencies else None},'ticket_states':{s:sum(t.status==s for t in tickets) for s in ('queued','assigned','resolved')},'negative_feedback':db.query(Feedback).filter_by(rating='down').count(),'approved_samples':db.query(TrainingSample).filter_by(status='approved').count(),'approved_knowledge':db.query(KnowledgeEntry).filter_by(status='approved').count()}

@router.get('/audits')
def audits():
    with SessionLocal() as db:
        return [{k:getattr(r,k) for k in ('id','kind','target','actor','detail','created_at')} for r in db.query(AuditEvent).order_by(AuditEvent.id.desc()).limit(100).all()]
