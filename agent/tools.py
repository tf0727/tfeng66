"""Business tools with session-bound persistence and traceable read-only facts."""
import json
from pathlib import Path
from harness.tools import Tool, ToolRegistry
from agent.samples import approved_samples
from agent.handoff import build_profile, summarize
from agent.ticket_store import create_ticket
from agent.knowledge import search_knowledge

ROOT=Path(__file__).resolve().parent.parent
PLAYBOOK_PATH=ROOT/'data/playbook.json'

def _load_playbook():
    # Compatibility UI shape, now derived exclusively from reviewed samples.
    return [{'id':str(r['id']),'scene':r['scene'],'keywords':[],'sample':r['answer'],'question':r['question'],'reason':r['reason']} for r in approved_samples()]

def recall_playbook(intent='',message=''):
    return approved_samples()

def analyze_student(message, context=''):
    return build_profile(context+'\n'+message)

def generate_plan(goal, level='待了解', available_time=''):
    return {'goal':goal,'level':level,'ability_path':['Python 基础','数据处理','自动化实践','项目实战'] if 'python' in goal.lower() else ['编程基础','核心语法','项目实战','作品整理'],'note':'能力路径示例，不包含招生政策或就业承诺。'}

def course_search(query='', keyword='', course_id=''):
    rows=json.loads((ROOT/'data/catalog.json').read_text(encoding='utf-8'))
    text=query or keyword
    hits=[r for r in rows if (not course_id or r['id']==course_id) and (not text or any(t.lower() in json.dumps(r,ensure_ascii=False).lower() for t in text.split()))]
    return {'matches':hits,'demo':True,'note':'人工登记的模拟商品资料，不代表真实机构政策；价格仍由班主任确认。'}

def student_cases(city, background='', direction=''):
    rows=json.loads((ROOT/'data/student_cases.json').read_text(encoding='utf-8'))
    hits=[r for r in rows if r.get('verified') and r.get('source') and r.get('city')==city and (not background or background in r.get('background','')) and (not direction or direction in r.get('direction',''))]
    return {'matches':hits,'note':'没有经核验案例时，不得虚构成功案例或就业结果。'}

def handoff(reason, summary, student_profile=None, session_id='', confidence=None):
    return create_ticket(session_id,reason,summary,student_profile,confidence)

def build_registry(session_id='', history='', samples=None, knowledge=None, read_only=False):
    registry=ToolRegistry()
    def add(name,description,properties,required,handler):
        registry.register(Tool(name,description,{'type':'object','properties':properties,'required':required,'additionalProperties':False},handler))
    s={'type':'string'}
    add('recall_playbook','取回全部已审核教学样本（问题、答案、原因），每轮程序强制执行。',{'intent':s,'message':s},[],lambda **_: samples if samples is not None else approved_samples())
    add('analyze_student','了解当前会话背景，不从缺失信息推断。',{'message':s,'context':s},['message'],analyze_student)
    add('generate_plan','仅生成能力路径，不包含招生政策或价格。',{'goal':s,'level':s,'available_time':s},['goal'],generate_plan)
    add('course_search','按关键词查询已登记模拟商品资料，空结果不能编造。',{'query':s,'keyword':s,'course_id':s},[],course_search)
    add('student_cases','仅查询已核验、有来源且背景匹配的真实案例。',{'city':s,'background':s,'direction':s},['city'],student_cases)
    add('knowledge_search','本地向量检索已审核知识并返回来源、版本。',{'query':s},['query'],lambda query:search_knowledge(query,knowledge))
    def transfer(reason,summary='',student_profile=None,confidence=None):
        profile=build_profile(history) if history.strip() else (student_profile or {})
        if read_only: return {'status':'simulated','reason':reason,'summary':summarize(summary or history),'student_profile':profile}
        return create_ticket(session_id,reason,summarize(summary or history),profile,confidence)
    add('handoff','用户明确要求、事实缺失或低置信度时创建真实工单。',{'reason':s,'summary':s,'student_profile':{'type':'object'},'confidence':{'type':'number','minimum':0,'maximum':1}},['reason'],transfer)
    def assess(confidence,reason):
        result={'confidence':confidence,'reason':reason,'source':'model_self_report'}
        if confidence < .5: result['handoff']=transfer('low_confidence: '+reason,confidence=confidence)
        return result
    add('assess_confidence','客观事实不足或无法可靠回答时报告自评；低于 0.5 自动转人工。',{'confidence':{'type':'number','minimum':0,'maximum':1},'reason':s},['confidence','reason'],assess)
    def order(order_id):
        rows=json.loads((ROOT/'data/demo_orders.json').read_text(encoding='utf-8'))
        row=next((r for r in rows if r['order_id']==order_id and r['session_id']==session_id),None)
        return {k:v for k,v in row.items() if k!='session_id'} if row else {'found':False,'message':'未找到本会话可访问的订单，不可查询他人订单。'}
    add('order_query','查询绑定当前会话的只读脱敏模拟订单。',{'order_id':s},['order_id'],order)
    return registry
