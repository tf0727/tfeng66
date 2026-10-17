"""Business composition root for the generic harness."""
from harness.loop import AgentLoop
from harness.llm import QwenClient
from agent.prompt import SYSTEM_PROMPT_V1
from agent.prompt_store import active_prompt_state, compose_system_prompt
from agent.sample_prompt import build_training_system_prompt
from agent.samples import approved_samples, sample_version
from agent.tools import build_registry
from agent.output_guard import sentence_policy
from uuid import uuid4

class ConsultantLoop(AgentLoop):
    def __init__(self,client=None,system_prompt=SYSTEM_PROMPT_V1,session_id='',history=None,knowledge=None,read_only=False,samples=None,cancelled=lambda:False,prompt_version=None):
        self._custom_prompt=system_prompt if system_prompt!=SYSTEM_PROMPT_V1 or prompt_version is not None else None
        self.snapshot_samples=samples
        self.session_id=session_id or 'cli-'+uuid4().hex
        self.knowledge=knowledge
        self.read_only=read_only
        self.forced_version=prompt_version
        self.current_input=''
        super().__init__(client or QwenClient(),build_registry(session_id),self.context_state,mandatory_tools=[('recall_playbook',{})],sanitize=sentence_policy,history=history,cancelled=cancelled)

    def context_state(self):
        state=active_prompt_state()
        samples=approved_samples() if self.snapshot_samples is None else self.snapshot_samples
        base=self._custom_prompt if self._custom_prompt is not None else state['content']
        history='\n'.join(m.get('content') or '' for m in self.messages if m['role']=='user')+'\n'+self.current_input
        self.registry=build_registry(self.session_id,history,samples,self.knowledge,self.read_only)
        content=compose_system_prompt(base,samples)
        return {'content':content,'prompt_version':self.forced_version if self.forced_version is not None else ('custom' if self._custom_prompt else state['version']),'sample_version':sample_version(samples),'sample_count':len(samples),'system_characters':len(content),'history_messages':len(self.messages)}

    def run_with_tools(self,user_input,max_rounds=6,prepared=False):
        self.current_input=user_input
        if prepared:
            # Refresh handlers with the current user's facts; retain frozen system context.
            self.context_state()
        yield from super().run_with_tools(user_input,max_rounds,prepared)
