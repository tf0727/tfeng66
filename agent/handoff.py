"""Deterministic handoff rules used before model generation."""
import re
from agent.sentiment import detect_sentiment, intent_strength

HANDOFF_PATTERNS = {
    "explicit_request": r"转人工|找客服|班主任联系|人工客服|联系班主任",
    "sensitive": r"我要退款|申请退款|要求退款|我要投诉|维权",
    "negative": r"太差了|我很生气|不想聊了",
}

def should_handoff(text: str) -> tuple[bool, str]:
    for reason, pattern in HANDOFF_PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            return True, reason
    return False, ""

def build_profile(text: str) -> dict[str, str]:
    return {
        "goal": "转行" if re.search(r"转行|就业", text) else "待了解",
        "education": "大专" if "大专" in text else ("本科" if "本科" in text else "未提及"),
        "city": next((x for x in ("北京", "上海", "广州", "深圳") if x in text), "未提及"),
        "intent": intent_strength(text),
        "sentiment": detect_sentiment(text),
        "level": '零基础' if re.search(r'零基础|没学过|没有基础', text) else ('有接触' if re.search(r'学过|接触过|做过开发', text) else '未提及'),
        "learning_time": next(iter(re.findall(r'(?:每天|每周)[^，。\n]{0,15}', text)), '未提及'),
        "budget_or_salary": next(iter(re.findall(r'(?:预算|月薪|工资|薪资)[^，。\n]{0,20}', text)), '未提及'),
        "graduation": next(iter(re.findall(r'(?:\d{2,4}届|毕业[^，。\n]{0,12})', text)), '未提及'),
        "background": next(iter(re.findall(r'(?:之前|现在|专业)[^，。\n]{0,25}', text)), '未提及'),
    }

def summarize(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned if len(cleaned)<=200 else '历史摘录：'+cleaned[:65]+'；最近诉求：'+cleaned[-115:]
