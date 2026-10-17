import unittest
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, TrainingSample
from agent.runtime import ConsultantLoop as AgentLoop


class FakeClient:
    def __init__(self):
        self.contexts = []

    def stream(self, messages, tools=None):
        self.contexts.append([dict(m) for m in messages])
        if tools is None:
            yield "测试回复"
        else:
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="测试回复", tool_calls=[]))])


class TrainingContextTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.patcher = patch("agent.samples.SessionLocal", self.sessions)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.engine.dispose()

    def test_approved_only_and_refresh_existing_conversation(self):
        with self.sessions() as db:
            row = TrainingSample(question="学费？", answer="先确认目标", reason="避免跳过意向确认", scene="价格", status="pending")
            db.add(row)
            db.commit()
            sample_id = row.id
        client = FakeClient()
        loop = AgentLoop(client=client, system_prompt="基础铁律")
        list(loop.run_with_tools("多少钱"))
        self.assertNotIn("避免跳过意向确认", client.contexts[-1][0]["content"])
        with self.sessions() as db:
            db.get(TrainingSample, sample_id).status = "approved"
            db.commit()
        list(loop.run_with_tools("继续"))
        context = client.contexts[-1]
        self.assertIn("避免跳过意向确认", context[0]["content"])
        self.assertIn("先确认目标", context[0]["content"])
        self.assertEqual(sum(m["role"] == "system" for m in context), 1)
        self.assertTrue(any(m.get("content") == "多少钱" for m in context[1:]))
        list(loop.run("再回答"))
        self.assertIn("避免跳过意向确认", client.contexts[-1][0]["content"])


if __name__ == "__main__":
    unittest.main()
