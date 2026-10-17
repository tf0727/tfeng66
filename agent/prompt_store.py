from db.models import PromptVersion, SessionLocal
from agent.prompt import SYSTEM_PROMPT_V1

def active_prompt() -> str:
    return active_prompt_state()["content"]


def active_prompt_state() -> dict:
    with SessionLocal() as db:
        row = db.query(PromptVersion).filter_by(status="active").order_by(PromptVersion.version.desc()).first()
        return {"content": row.content if row else SYSTEM_PROMPT_V1, "version": row.version if row else 0}


RUNTIME_POLICY = '\n\n运行约束：需要事实时调用已注册工具；不虚构真实案例。客观事实不足或无法可靠回答时调用 assess_confidence 报告自评；低于0.5自动建单。模型自评不是客观正确率。只使用工具 schema 中实际注册的工具。'

def compose_system_prompt(base: str, samples=None) -> str:
    from agent.sample_prompt import build_training_system_prompt
    return base + "\n\n" + build_training_system_prompt(samples) + RUNTIME_POLICY
