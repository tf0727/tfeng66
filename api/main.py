"""HTTP composition root, local observability and packaged frontend."""
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from api.chat import router as chat_router
from api.admin import router as admin_router
from db.models import Message, Session, SessionLocal
from agent.jobs import recover_interrupted

logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(name)s %(message)s')

@asynccontextmanager
async def lifespan(app):
    recover_interrupted()
    yield

app=FastAPI(title='Programming Consultant Agent',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:5173','http://127.0.0.1:5173'],allow_methods=['*'],allow_headers=['*'])
app.include_router(chat_router)
app.include_router(admin_router)

@app.get('/health')
def health(): return {'status':'ok'}

@app.get('/sessions/{session_id}')
def session_history(session_id:str):
    with SessionLocal() as db:
        rows=db.query(Message).filter(Message.session_id==session_id).order_by(Message.id).all()
        session=db.get(Session,session_id)
        return {'session_id':session_id,'profile':json.loads(session.profile) if session else {},'messages':[{k:getattr(r,k) for k in ('id','role','content','request_id','prompt_version')} for r in rows]}

@app.get('/api/health')
def api_health(): return health()

# Production API prefix shares exactly the same routes as development proxy.
app.include_router(chat_router,prefix='/api')
app.include_router(admin_router,prefix='/api')
app.add_api_route('/api/sessions/{session_id}',session_history,methods=['GET'])
dist=Path(__file__).resolve().parent.parent/'frontend/dist'
if dist.exists(): app.mount('/',StaticFiles(directory=dist,html=True),name='frontend')
