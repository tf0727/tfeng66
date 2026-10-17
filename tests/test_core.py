from agent.handoff import build_profile, should_handoff
from agent.prompt_parser import parse_prompt
from agent.output_guard import guard_output

def test_price_guard():
    assert "8888" not in guard_output("价格是8888元")

def test_handoff_rules():
    assert should_handoff("我要退款")[0]
    assert not should_handoff("我想学 Python")[0]

def test_prompt_sections():
    assert not parse_prompt("## 铁律\n1. 不报价\n## 语气\n简洁").validate()

def test_profile():
    assert build_profile("我确定报名，人在上海")["intent"] == "high"
