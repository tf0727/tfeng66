"""Business policy filters, called only on complete sentences or complete replies."""
import re

NO_PRICE = "价格和优惠由班主任一对一确认。您是认真考虑学习，还是先了解一下？"
PRICE = re.compile(r"[￥¥$]\s*\d|\d[\d,.]*\s*(?:元|块|万|千|[kKwW](?![a-zA-Z]))|[一二三四五六七八九十百千万两]+\s*(?:元|块钱)|(?:价格|学费|报价|费用|收费|优惠价)\s*(?:是|为|只要|仅需|[:：])?\s*\d")
PUSH = re.compile(r"(?:立即|马上|赶紧).*(?:报名|付款|下单)")
PROMISE = re.compile(r"(?:保证|确保|百分百|100%).*(?:就业|找到工作|通过|学会)|我们包(?:就业|过)")

def sentence_policy(text: str) -> str:
    if PRICE.search(text): return NO_PRICE
    if PUSH.search(text): return "您可以先明确学习目标，再与班主任确认合适的安排。"
    if PROMISE.search(text): return "学习效果和就业情况需要结合个人基础与投入，具体政策由班主任确认。"
    return text

def guard_output(text: str, max_sentences: int = 3) -> str:
    safe = sentence_policy(text)
    parts = re.findall(r"[^。！？!?]+[。！？!?]?", safe)
    return "".join(parts[:max_sentences]).strip()
