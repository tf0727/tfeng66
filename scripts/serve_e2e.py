"""Isolated deterministic server exclusively for browser integration tests."""
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as Obj

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))

class TestClient:
    def stream(self,messages,tools=None):
        for part in ['先了解您的学习目标。','再结合基础规划学习路径。']:
            yield Obj(choices=[Obj(delta=Obj(content=part,tool_calls=[]))])
    def complete(self,messages,json_mode=False):
        if json_mode:
            return '{"candidate":"## 铁律\\n1. 不报价，先确认目标。\\n## 语气\\n先回应重点，保持简短。","rationale":"根据差评缩短回答"}'
        return '先了解学习目标，具体政策由班主任确认。'

if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='consultant-browser-') as temp:
        os.environ['APP_DB_PATH']=str(Path(temp)/'test.db')
        os.environ['OPTIMIZE_THRESHOLD']='100'
        import agent.runtime
        import harness.llm
        agent.runtime.QwenClient=TestClient
        harness.llm.QwenClient=TestClient
        from db.models import SessionLocal,PromptVersion,TrainingSample,engine
        from agent.prompt import SYSTEM_PROMPT_V1
        with SessionLocal() as db:
            db.add(PromptVersion(version=1,content=SYSTEM_PROMPT_V1,status='active'))
            db.add(TrainingSample(question='怎么学',answer='先了解目标',reason='确认需求',status='approved'))
            db.commit()
        import uvicorn
        try: uvicorn.run('api.main:app',host='127.0.0.1',port=8899)
        finally: engine.dispose()
