import re

NEGATIVE = ("生气", "愤怒", "投诉", "骗人", "太差", "失望", "退款")

def detect_sentiment(text: str) -> str:
    return "negative" if any(word in text for word in NEGATIVE) else "neutral"

def intent_strength(text: str) -> str:
    if re.search(r"报名|确定|认真|马上学|真想", text): return "high"
    if re.search(r"想学|了解|考虑", text): return "medium"
    return "low"
