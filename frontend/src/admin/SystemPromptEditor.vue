<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

type Version = { version: number; status: string; content: string }
const api = '/api/admin'
const content = ref(''), original = ref(''), fullPrompt = ref(''), trainingPrompt = ref('')
const version = ref(0), sampleCount = ref(0), versions = ref<Version[]>([])
const busy = ref(false), error = ref(''), notice = ref('')
const proposals = ref<any[]>([]), smokeReport = ref<any>(null)
const dirty = computed(() => content.value !== original.value)
const title = computed(() => version.value ? `v${version.value}` : '默认内置版本')

async function request(path: string, options?: RequestInit) {
  const response = await fetch(api + path, options)
  const data = await response.json()
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail))
  return data
}
async function load() {
  const [context, history] = await Promise.all([request('/prompts/context'), request('/prompts')])
  content.value = original.value = context.content
  fullPrompt.value = context.full_prompt
  trainingPrompt.value = context.training_prompt
  version.value = context.version
  sampleCount.value = context.approved_samples
  versions.value = history.versions
  proposals.value = history.proposals
}
async function action(work: () => Promise<void>) {
  busy.value = true; error.value = ''; notice.value = ''
  try { await work() } catch (e) { error.value = e instanceof Error ? e.message : '请求失败' }
  finally { busy.value = false }
}
function refresh() {
  if (dirty.value && !confirm('刷新将放弃未保存修改，继续吗？')) return
  action(load)
}
function preview() {
  action(async () => {
    const data = await request('/prompts/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content: content.value }) })
    fullPrompt.value = data.full_prompt
    notice.value = '已更新完整预览；当前修改尚未发布。'
  })
}
function save() {
  action(async () => {
    const result = await request('/prompts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content: content.value, base_version: version.value }) })
    await load()
    notice.value = `v${result.version} 已发布，当前会话下一轮回答生效。`
  })
}
function smoke() { action(async () => { smokeReport.value = await request('/prompts/smoke', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({content:content.value}) }); notice.value='真实模型红线测试已完成。' }) }
function optimize() { action(async () => { const result=await request('/prompts/optimize',{method:'POST'}); await load(); notice.value=result.reason || '已生成模型优化建议，尚未发布。' }) }
function review(id:number, decision:string) { action(async () => { await request(`/prompts/proposals/${id}/${decision}`,{method:'POST'}); await load(); notice.value=decision==='approve'?'建议已通过模型红线测试并发布。':'建议已拒绝。' }) }
function rollback(target: number) {
  if (!confirm(`切换到 v${target}？未保存的编辑将被放弃。`)) return
  action(async () => { await request(`/prompts/${target}/rollback`, { method: 'POST' }); await load(); notice.value = `已回滚到 v${target}，下一轮回答生效。` })
}
function editVersion(item: Version) {
  if (dirty.value && !confirm('使用此版本内容覆盖未保存的编辑？')) return
  content.value = item.content
  notice.value = `已载入 v${item.version} 供编辑，点击保存后发布新版本。`
}
function download() {
  const url = URL.createObjectURL(new Blob([fullPrompt.value], { type: 'text/markdown;charset=utf-8' }))
  const link = document.createElement('a'); link.href = url; link.download = `system-prompt-v${version.value}.md`; link.click(); URL.revokeObjectURL(url)
}
onMounted(() => action(load))
</script>

<template>
  <div class="prompt-editor">
    <div class="overview">
      <div><strong>生效版本：{{ title }}</strong><p>完整系统提示词 = 基础 Prompt + 已审核训练样本套路（{{ sampleCount }} 条）。</p></div>
      <button :disabled="busy" @click="refresh">刷新内容</button>
    </div>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="notice" class="notice" role="status">{{ notice }}</p>
    <section>
      <h2>编辑基础 Prompt <small v-if="dirty">有未保存修改</small></h2>
      <p>可修改人设、流程、铁律和语气。保留非空的「## 铁律」与「## 语气」；保存通过校验后生成新版本。</p>
      <textarea v-model="content" :disabled="busy" aria-label="基础系统提示词" spellcheck="false" />
      <div class="actions"><button :disabled="busy || !content.trim()" @click="save">校验、真实冒烟并发布</button><button class="secondary" :disabled="busy" @click="preview">预览完整上下文</button><button class="secondary" :disabled="busy" @click="smoke">真实模型红线测试</button></div>
      <pre v-if="smokeReport">{{ smokeReport }}</pre>
    </section>
    <section>
      <h2>训练样本生成的套路</h2>
      <p>此部分每轮自动生成。请到「训练样本」修改标注或审核样本，再刷新本页查看。</p>
      <pre>{{ trainingPrompt }}</pre>
    </section>
    <section>
      <h2>完整 System Prompt</h2>
      <p>与回答前的上下文组装共用同一个方法。编辑后点击预览可查看草稿；保存发布后下一轮生效。</p>
      <textarea :value="fullPrompt" readonly aria-label="完整系统提示词预览" spellcheck="false" />
      <button class="secondary" :disabled="!fullPrompt" @click="download">下载完整 Prompt</button>
    </section>
    <section><h2>版本历史</h2><p v-if="!versions.length">尚无保存版本，正在使用内置默认 Prompt。</p>
      <div v-for="item in versions" :key="item.version" class="version-row">
        <span>v{{ item.version }} · {{ item.status === 'active' ? '当前生效' : '历史版本' }}</span>
        <div class="actions"><button class="secondary" :disabled="busy" @click="editVersion(item)">载入编辑</button><button v-if="item.status !== 'active'" class="secondary" :disabled="busy" @click="rollback(item.version)">回滚此版本</button></div>
      </div>
    </section>
    <section><h2>差评驱动的优化建议</h2><p>使用未处理差评、原回复及基准 Prompt 调用真实模型。默认累计 3 条差评后台触发，也可手动触发；候选与 diff 分开保存。</p><button :disabled="busy" @click="optimize">分析差评并生成建议</button>
      <div v-for="p in proposals" :key="p.id" class="version-row"><div><b>#{{p.id}} · {{p.status}} · 基准 v{{p.base_version}}</b><p>{{p.rationale}}</p><pre>{{p.diff}}</pre><details><summary>完整候选 Prompt</summary><pre>{{p.candidate || '旧版建议缺少独立候选内容，需重新生成。'}}</pre></details><div v-if="p.status==='pending'" class="actions"><button :disabled="busy||!p.candidate" @click="review(p.id,'approve')">测试并批准</button><button class="secondary" :disabled="busy" @click="review(p.id,'reject')">拒绝</button></div></div></div>
    </section>
  </div>
</template>

<style scoped>
.prompt-editor { max-width: 1000px; }
.overview,.version-row,.actions { display:flex; gap:12px; align-items:center; flex-wrap:wrap; }
.overview,.version-row { justify-content:space-between; }
section { background:white; border:1px solid #e2e5ed; border-radius:12px; padding:24px; margin:18px 0; }
h2 { font-size:18px; margin:0 0 10px; } h2 small { color:#a56200; font-size:12px; }
p { color:#667085; line-height:1.7; font-size:13px; }
textarea,pre { width:100%; padding:16px; border:1px solid #dfe3eb; border-radius:8px; font:13px/1.8 Consolas,"Microsoft YaHei",monospace; background:#fafbfe; color:#172033; }
textarea { min-height:320px; resize:vertical; margin-bottom:12px; } pre { white-space:pre-wrap; overflow-wrap:anywhere; max-height:400px; overflow:auto; }
button { border:0; background:#6d5dfc; color:#fff; border-radius:8px; padding:10px 14px; cursor:pointer; }
button.secondary { background:#efedff; color:#5946d8; } button:disabled { opacity:.5; cursor:wait; }
.error { color:#b42318; background:#fee4e2; padding:12px; border-radius:8px; }
.notice { color:#067647; background:#dcfae6; padding:12px; border-radius:8px; }
.version-row { border-top:1px solid #eee; padding:14px 0; }
</style>
