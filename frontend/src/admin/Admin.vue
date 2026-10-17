<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import PageSwitcher from '../components/PageSwitcher.vue'
import SystemPromptEditor from './SystemPromptEditor.vue'
import { request, json } from '../api/client'

const tab=ref('tickets'),busy=ref(false),error=ref(''),notice=ref('')
const tickets=ref<any[]>([]),samples=ref<any[]>([]),knowledge=ref<any[]>([]),runs=ref<any[]>([]),versions=ref<any[]>([]),audits=ref<any[]>([]),metrics=ref<any>({})
const form=ref({question:'',answer:'',reason:'',scene:'通用',source:'人工录入'}),editId=ref<number|null>(null)
const kform=ref({question:'',answer:'',source:''}),knowledgeId=ref<number|null>(null)
const selectedRun=ref(''),selectedVersion=ref(0),knowledgeMode=ref('snapshot'),comparison=ref<any>(null)
const tabs:Record<string,string>={tickets:'工单管理',playbook:'审核套路库',training:'训练样本',knowledge:'知识审核与检索',prompt:'系统提示词',replay:'同题回放',metrics:'运行指标与审计'}
const approved=computed(()=>samples.value.filter(s=>s.status==='approved'))
async function load(){
  const data=await Promise.all(['/admin/tickets','/admin/training-samples','/admin/knowledge','/admin/runs','/admin/prompts','/admin/audits','/admin/metrics'].map(p=>request(p)))
  ;[tickets.value,samples.value,knowledge.value,runs.value]=data
  versions.value=data[4].versions;audits.value=data[5];metrics.value=data[6]
  if(!selectedVersion.value)selectedVersion.value=versions.value.find(v=>v.status==='active')?.version || 0
}
async function act(work:()=>Promise<void>){
  busy.value=true;error.value='';notice.value=''
  try{await work()}catch(e){error.value=e instanceof Error?e.message:'请求失败'}finally{busy.value=false}
}
function reset(){editId.value=null;form.value={question:'',answer:'',reason:'',scene:'通用',source:'人工录入'}}
function edit(s:any){editId.value=s.id;form.value={question:s.question,answer:s.answer,reason:s.reason,scene:s.scene,source:s.source};tab.value='training'}
function saveSample(){act(async()=>{
  await request('/admin/training-samples'+(editId.value?'/'+editId.value:''),json(editId.value?'PUT':'POST',form.value))
  reset();await load();notice.value='样本已保存为待审核；审核后下一轮生效。'
})}
function review(s:any,status:string){
  let acknowledge=false
  if(status==='approved'&&s.warnings.length){acknowledge=confirm(s.warnings.join('\n')+'\n确认仍审核通过？业务铁律始终优先。');if(!acknowledge)return}
  const note=prompt('审核意见（可选）','') || ''
  act(async()=>{await request('/admin/training-samples/'+s.id+'?'+new URLSearchParams({status,acknowledge:String(acknowledge),note}),{method:'PATCH'});await load()})
}
function removeSample(s:any){if(confirm('删除此样本？下轮上下文将移除，审计记录保留。'))act(async()=>{await request('/admin/training-samples/'+s.id,{method:'DELETE'});await load()})}
function ticketStatus(t:any){act(async()=>{await request('/admin/tickets/'+t.id+'?status='+(t.status==='queued'?'assigned':'resolved'),{method:'PATCH'});await load()})}
function saveKnowledge(){act(async()=>{await request('/admin/knowledge'+(knowledgeId.value?'/'+knowledgeId.value:''),json(knowledgeId.value?'PUT':'POST',kform.value));knowledgeId.value=null;kform.value={question:'',answer:'',source:''};await load();notice.value='知识已进入审核队列，尚未参与检索。'})}
function editKnowledge(k:any){knowledgeId.value=k.id;kform.value={question:k.question,answer:k.answer,source:k.source}}
function reviewKnowledge(k:any,status:string){const note=prompt('审核意见（可选）','')||'';act(async()=>{await request('/admin/knowledge/'+k.id+'?'+new URLSearchParams({status,note}),{method:'PATCH'});await load();notice.value=status==='approved'?'已确认入库并建立本地向量索引。':'已拒绝入库。'})}
function archiveKnowledge(k:any){if(confirm('撤回此知识？将从向量检索中移除。'))act(async()=>{await request('/admin/knowledge/'+k.id,{method:'DELETE'});await load()})}
function replay(){act(async()=>{comparison.value=await request('/admin/replays',json('POST',{run_id:selectedRun.value,prompt_version:Number(selectedVersion.value),knowledge_mode:knowledgeMode.value}));await load()})}
function exportMetrics(){const url=URL.createObjectURL(new Blob([JSON.stringify(metrics.value,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='local-metrics.json';a.click();URL.revokeObjectURL(url)}
onMounted(()=>act(load))
</script>

<template>
  <div class="admin"><PageSwitcher destination="consultation" />
    <aside><h2>CodePath 后台</h2><p>本地咨询运营与调试</p><button v-for="(label,key) in tabs" :key="key" :class="{active:tab===key}" @click="tab=String(key)">{{label}}</button><a href="/">返回咨询平台</a></aside>
    <main><header><h1>{{tabs[tab]}}</h1><button :disabled="busy" @click="act(load)">刷新</button></header>
      <p v-if="error" class="error" role="alert">{{error}}</p><p v-if="notice" class="notice">{{notice}}</p>
      <section v-if="tab==='tickets'">
        <p>工单按“排队 → 已接单 → 已处理”推进；不同触发路径共用存储与去重。</p>
        <article v-for="t in tickets" :key="t.id"><h3>{{t.id}} <small>{{t.status}}</small></h3><p>{{t.reason}} · {{t.created_at}}</p><p>{{t.summary}}</p><pre>{{t.student_profile}}</pre><p v-if="t.confidence">模型自评：{{t.confidence}}（非客观正确率）</p><button v-if="t.status!=='resolved'" :disabled="busy" @click="ticketStatus(t)">{{t.status==='queued'?'接单':'标记已处理'}}</button></article>
        <p v-if="!tickets.length">暂无工单。</p>
      </section>
      <section v-else-if="tab==='playbook'">
        <p>与训练样本和每轮 recall_playbook 共用同一数据源。此处只展示已审核样本。</p>
        <button @click="tab='training';reset()">新增教学样本</button>
        <article v-for="s in approved" :key="s.id"><h3>{{s.scene}}</h3><p>问题：{{s.question}}</p><p>答案：{{s.answer}}</p><p>原因：{{s.reason}}</p><button @click="edit(s)">编辑（重新审核）</button></article>
      </section>
      <section v-else-if="tab==='training'">
        <form class="card" @submit.prevent="saveSample"><h3>{{editId?'编辑 #'+editId:'新增训练样本'}}</h3><label>学员问题<input v-model="form.question" required /></label><label>标注答案<textarea v-model="form.answer" required /></label><label>这么回答的原因<textarea v-model="form.reason" required /></label><label>场景<input v-model="form.scene" required /></label><label>来源<input v-model="form.source" required /></label><button :disabled="busy">保存并提交审核</button><button type="button" class="secondary" @click="reset">取消编辑</button></form>
        <article v-for="s in samples" :key="s.id"><h3>#{{s.id}} · {{s.scene}} · {{s.status}}</h3><p>问：{{s.question}}</p><p>答：{{s.answer}}</p><p>因：{{s.reason}}</p><p>来源：{{s.source}} · {{s.reviewer}} {{s.reviewed_at}} {{s.review_note}}</p><p v-for="w in s.warnings" :key="w" class="warning">{{w}}</p><div class="actions"><button @click="edit(s)">编辑</button><button v-if="s.status!=='approved'" :disabled="busy" @click="review(s,'approved')">审核通过</button><button v-if="s.status!=='rejected'" :disabled="busy" @click="review(s,'rejected')">驳回 / 撤回</button><button class="danger" :disabled="busy" @click="removeSample(s)">删除</button></div></article>
      </section>
      <section v-else-if="tab==='knowledge'">
        <p>人工填答 → 审核队列 → 确认入库。仅已审核知识参与本地向量检索。索引使用字符二元组哈希，无需下载模型；相关度不是置信度。</p>
        <form class="card" @submit.prevent="saveKnowledge"><h3>{{knowledgeId?'编辑知识 #'+knowledgeId:'新增知识'}}</h3><label>问题<input v-model="kform.question" required /></label><label>事实答案<textarea v-model="kform.answer" required /></label><label>可核验来源<input v-model="kform.source" placeholder="文档名、人工确认人或链接" required /></label><button :disabled="busy">提交审核</button></form>
        <article v-for="k in knowledge" :key="k.id"><h3>#{{k.id}} · v{{k.version}} · {{k.status}}</h3><p>{{k.question}}</p><p>{{k.answer}}</p><p>{{k.source}} · {{k.reviewer}} {{k.reviewed_at}}</p><div class="actions"><button @click="editKnowledge(k)">编辑</button><button v-if="k.status==='pending'" @click="reviewKnowledge(k,'approved')">确认入库</button><button v-if="k.status==='pending'" @click="reviewKnowledge(k,'rejected')">拒绝</button><button class="danger" @click="archiveKnowledge(k)">撤回</button></div></article>
      </section>
      <SystemPromptEditor v-else-if="tab==='prompt'" />
      <section v-else-if="tab==='replay'">
        <div class="card"><p>选择原始请求与 Prompt 版本。回放使用真实模型，工具为只读模式，不会产生新工单。</p><label>原问题<select v-model="selectedRun"><option disabled value="">请选择</option><option v-for="r in runs.filter(r=>r.status!=='running')" :key="r.id" :value="r.id">{{r.question}} · {{r.mode}} · v{{r.prompt_version}}</option></select></label><label>Prompt 版本<select v-model="selectedVersion"><option :value="0">内置默认</option><option v-for="v in versions" :key="v.version" :value="v.version">v{{v.version}} · {{v.status}}</option></select></label><label>知识与教学样本<select v-model="knowledgeMode"><option value="snapshot">原请求快照</option><option value="current">当前审核版本</option></select></label><button :disabled="busy||!selectedRun" @click="replay">{{busy?'真实模型回放中…':'运行对比'}}</button></div>
        <div v-if="comparison" class="comparison"><article><h3>原始回复</h3><p>{{comparison.original}}</p></article><article><h3>回放回复</h3><p>{{comparison.reply}}</p></article></div><article v-if="comparison"><h3>差异</h3><pre>{{comparison.diff||'文本无差异'}}</pre><details><summary>回放工具与决策摘要</summary><pre>{{comparison.trace}}</pre></details></article>
      </section>
      <section v-else><div class="card"><h3>本地技术运行指标</h3><p>不把兜底回复计为真实模型成功，不将本地调用量解释为真实用户量。</p><pre>{{metrics}}</pre><button @click="exportMetrics">导出指标 JSON</button></div><article v-for="a in audits" :key="a.id"><b>{{a.kind}} · {{a.target}}</b><p>{{a.actor}} · {{a.created_at}}</p><details><summary>查看审计详情</summary><pre>{{a.detail}}</pre></details></article></section>
    </main>
  </div>
</template>
<style scoped>
.admin{display:flex;min-height:100vh;background:#f5f7fb;color:#172033;font:14px/1.6 "Microsoft YaHei",sans-serif}
aside{width:230px;flex-shrink:0;background:#111827;color:#fff;padding:28px 18px;display:flex;flex-direction:column;gap:8px}
aside h2{font-size:19px;margin:0}aside p{color:#8993a4;font-size:12px}aside button,aside a{padding:12px;text-align:left;background:transparent;color:#abb7ca;border:0;border-radius:8px;text-decoration:none}aside .active{background:#6d5dfc;color:white}aside a{margin-top:auto}
main{flex:1;min-width:0;padding:38px 5%;max-width:1300px}header{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px}h1{font-size:24px}h3{margin:0 0 10px}
article,.card{background:#fff;border:1px solid #e3e7f0;border-radius:12px;padding:22px;margin:14px 0}
label{display:block;font-size:13px;margin:12px 0}input,textarea,select{display:block;width:100%;border:1px solid #dbe0ea;padding:11px;border-radius:8px;margin:6px 0;font:inherit}textarea{min-height:90px;resize:vertical}
button{border:0;border-radius:8px;background:#6d5dfc;color:#fff;padding:9px 14px;cursor:pointer}button:disabled{opacity:.5;cursor:wait}.actions{display:flex;gap:8px;flex-wrap:wrap}.secondary{background:#eee;color:#333}.danger{background:#fff0ef;color:#b42318}.error,.warning{background:#fff0ef;color:#b42318;padding:10px}.notice{background:#dcfae6;color:#067647;padding:10px}
pre{font:12px/1.6 Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere;max-height:400px;overflow:auto}p{overflow-wrap:anywhere}.comparison{display:grid;grid-template-columns:1fr 1fr;gap:16px}
</style>
