import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.main import app
from db.models import Base, PromptVersion, TrainingSample
from agent.runtime import ConsultantLoop as AgentLoop


class PromptEditorTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        for module in ("api.admin", "agent.prompt_store", "agent.samples"):
            patcher = patch(module + ".SessionLocal", self.sessions)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(app)
        smoke = patch('api.admin.model_smoke_tests', return_value={'passed': True, 'results': [], 'mode': 'test_stub'})
        smoke.start()
        self.addCleanup(smoke.stop)
        self.content = "## 铁律\n1. 不报价，先确认学习意向。\n## 语气\n简洁自然。"

    def tearDown(self):
        self.engine.dispose()

    def test_preview_publish_refresh_and_rollback(self):
        with self.sessions() as db:
            db.add(TrainingSample(question="学什么", answer="了解目标", reason="匹配方向", status="approved"))
            db.commit()
        initial = self.client.get('/admin/prompts/context').json()
        self.assertIn("匹配方向", initial['full_prompt'])
        result = self.client.post('/admin/prompts', json={'content': self.content, 'base_version': 0})
        self.assertEqual(result.status_code, 200)
        loop = AgentLoop(client=object())
        loop.prepare_context()
        self.assertEqual(loop.messages[0]['content'], self.client.get('/admin/prompts/context').json()['full_prompt'])
        changed = self.content + '\n多用 emoji。'
        preview = self.client.post('/admin/prompts/preview', json={'content': changed}).json()
        self.assertIn('emoji', preview['full_prompt'])
        self.client.post('/admin/prompts', json={'content': changed, 'base_version': 1}).raise_for_status()
        loop.prepare_context()
        self.assertIn('emoji', loop.messages[0]['content'])
        self.assertEqual(self.client.post('/admin/prompts', json={'content': changed, 'base_version': 1}).status_code, 409)
        with self.sessions() as db:
            self.assertEqual(db.query(PromptVersion).filter_by(status='active').count(), 1)
        self.client.post('/admin/prompts/1/rollback').raise_for_status()
        loop.prepare_context()
        self.assertNotIn('emoji', loop.messages[0]['content'])
        self.assertEqual(self.client.post('/admin/prompts', json={'content': '## 铁律\n\n## 语气\n'}).status_code, 400)


if __name__ == '__main__':
    unittest.main()
