"""Business-independent streaming tool loop with injected context and policies."""
import json
from time import perf_counter
from uuid import uuid4
from harness.context import compact_history
from harness.guard import StreamingGuard

class AgentLoop:
    def __init__(self, client, registry, context_provider, mandatory_tools=(), sanitize=lambda text: text, history=None, cancelled=lambda: False):
        self.client, self.registry = client, registry
        self.context_provider = context_provider
        self.mandatory_tools = mandatory_tools
        self.sanitize = sanitize
        self.cancelled = cancelled
        self.messages = history or []
        self.context_info = {}

    def prepare_context(self):
        state = self.context_provider()
        history, summary = compact_history(self.messages)
        self.context_info = {k:v for k,v in state.items() if k != 'content'}
        self.messages = [{'role':'system','content':state['content'] + ('\n历史原文摘录（已裁剪）：\n'+summary if summary else '')}, *history]

    def _execute(self, name, args, call_id):
        start = perf_counter()
        yield {'type':'tool_start','call_id':call_id,'name':name,'arguments':args}
        try:
            result = self.registry.call(name,args)
            status = 'success'
        except Exception as exc:
            result = {'error':'工具执行失败','error_type':type(exc).__name__}
            status = 'error'
        yield {'type':'tool_end','call_id':call_id,'name':name,'result':result,'status':status,'elapsed_ms':round((perf_counter()-start)*1000)}
        self.messages.append({'role':'tool','tool_call_id':call_id,'content':json.dumps(result,ensure_ascii=False)})

    def run(self, user_input):
        for event in self.run_with_tools(user_input):
            if event['type']=='delta': yield event['content']

    def run_with_tools(self,user_input,max_rounds=6,prepared=False):
        if not prepared: self.prepare_context()
        yield {'type':'trace','stage':'context','summary':'已加载生效提示词、审核样本和会话历史。',**self.context_info}
        self.messages.append({'role':'user','content':user_input})
        # Program-enforced preflight, never delegated to model compliance.
        for name,args in self.mandatory_tools:
            call_id='preflight-'+uuid4().hex
            self.messages.append({'role':'assistant','content':None,'tool_calls':[{'id':call_id,'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]})
            yield from self._execute(name,args,call_id)
        guard = StreamingGuard(self.sanitize)
        answer = []
        for round_index in range(max_rounds):
            if self.cancelled(): raise InterruptedError('cancelled')
            yield {'type':'trace','stage':'model','round':round_index+1,'summary':'根据样本与当前上下文生成回复或调用事实工具。','available_tools':[t['function']['name'] for t in self.registry.schemas()]}
            calls, raw = {}, []
            for chunk in self.client.stream(self.messages,tools=self.registry.schemas()):
                if self.cancelled(): raise InterruptedError('cancelled')
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta: continue
                if delta.content:
                    raw.append(delta.content)
                    safe=guard.feed(delta.content)
                    if safe: answer.append(safe); yield {'type':'delta','content':safe}
                for call in delta.tool_calls or []:
                    item=calls.setdefault(call.index,{'id':call.id or '', 'name':'', 'arguments':''})
                    if call.id: item['id']=call.id
                    if call.function:
                        item['name']+=call.function.name or ''
                        item['arguments']+=call.function.arguments or ''
            if not calls:
                safe=guard.finish()
                if safe: answer.append(safe); yield {'type':'delta','content':safe}
                self.messages.append({'role':'assistant','content':''.join(answer)})
                if guard.changed: yield {'type':'trace','stage':'guard','status':'warning','summary':'已在完整句边界执行内容过滤或全局句数限制。'}
                return
            assistant_calls=[{'id':c['id'],'type':'function','function':{'name':c['name'],'arguments':c['arguments']}} for c in calls.values()]
            self.messages.append({'role':'assistant','content':''.join(raw) or None,'tool_calls':assistant_calls})
            for call in calls.values():
                try:
                    args=json.loads(call['arguments'] or '{}')
                except ValueError:
                    args={'__invalid_arguments__':call['arguments'][:100]}
                yield from self._execute(call['name'],args,call['id'])
        safe=guard.finish()
        if safe: yield {'type':'delta','content':safe}
        yield {'type':'trace','stage':'limit','status':'error','summary':'达到工具轮数上限，请缩小问题范围。'}

