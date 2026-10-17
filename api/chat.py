import asyncio
import json
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from agent.jobs import start_request, run_key
from db.models import ChatRun, SessionLocal

router=APIRouter()

class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1,max_length=100)
    message: str = Field(min_length=1,max_length=5000)
    request_id: str = Field(default_factory=lambda:uuid4().hex,max_length=100,min_length=1)
    after_seq: int = Field(default=0,ge=0)

def event(name,data,seq=None):
    return (f'id: {seq}\n' if seq is not None else '')+f'event: {name}\ndata: {json.dumps(data,ensure_ascii=False)}\n\n'

@router.post('/chat')
async def chat(body:ChatRequest,request:Request):
    try: key=start_request(body.session_id,body.request_id,body.message)
    except ValueError as exc: raise HTTPException(409,str(exc))
    except RuntimeError as exc: raise HTTPException(409,str(exc))
    async def stream():
        cursor=body.after_seq
        heartbeat=0
        while True:
            if await request.is_disconnected(): break
            with SessionLocal() as db:
                row=db.get(ChatRun,key)
                events=json.loads(row.events); status=row.status
            for item in events:
                if item['seq']>cursor:
                    yield event(item['event'],item['data'],item['seq'])
                    cursor=item['seq']
            if status!='running': break
            heartbeat+=1
            if heartbeat>=25:
                yield ': heartbeat\n\n'; heartbeat=0
            await asyncio.sleep(.2)
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

class CancelRequest(BaseModel):
    session_id:str
    request_id:str

@router.post('/chat/cancel')
def cancel(body:CancelRequest):
    with SessionLocal() as db:
        row=db.get(ChatRun,run_key(body.session_id,body.request_id))
        if not row: raise HTTPException(404,'请求不存在')
        row.cancel=1; db.commit()
        return {'status':'cancellation_requested'}
