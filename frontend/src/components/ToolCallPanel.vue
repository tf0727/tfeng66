<script setup lang="ts">
defineProps<{ tools: { question: string; events: any[] }[] }>()
const labels: Record<string, string> = {
  start: '开始', trace: '决策摘要', tool_start: '工具开始', tool_end: '工具结果',
  handoff: '转人工', error: '错误提示', done: '完成',
}
function time(value?: string) { return value ? new Date(value).toLocaleTimeString('zh-CN', { hour12: false }) : '' }
function details(item: any) {
  const { event_type, summary, timestamp, ...rest } = item
  return JSON.stringify(rest, null, 2)
}
</script>

<template>
  <section v-if="tools.length" class="execution-trace">
    <h3>Agent 执行轨迹 <small>调试视图</small></h3>
    <p>展示可核验的决策摘要、上下文信息和工具执行记录。</p>
    <details v-for="(turn, index) in tools" :key="index" :open="index === tools.length - 1">
      <summary>第 {{ index + 1 }} 轮 · {{ turn.question }} <span>{{ turn.events.length }} 个事件</span></summary>
      <ol>
        <li v-for="(item, eventIndex) in turn.events" :key="eventIndex" :class="{ failed: item.event_type === 'error' || item.status === 'error' }">
          <div class="trace-heading"><b>{{ labels[item.event_type] || item.event_type }}</b><code v-if="item.name">{{ item.name }}</code><time>{{ time(item.timestamp) }}</time></div>
          <div v-if="item.summary || item.message" class="trace-description">{{ item.summary || item.message }}</div>
          <details class="payload"><summary>查看参数与详情<span v-if="item.elapsed_ms !== undefined"> · {{ item.elapsed_ms }} ms</span></summary><pre>{{ details(item) }}</pre></details>
        </li>
      </ol>
    </details>
  </section>
</template>

<style scoped>
.execution-trace { margin-top:28px; padding:18px; border:1px solid #dce0ef; border-radius:12px; background:#fff; }
h3 { margin:0; font-size:15px; } h3 small { font-size:11px; color:#6d5dfc; margin-left:8px; }
p { color:#8993a4; font-size:12px; } summary { cursor:pointer; font-size:13px; line-height:1.8; overflow-wrap:anywhere; }
summary span { color:#8993a4; font-size:11px; } ol { list-style:none; padding:0 0 0 14px; border-left:2px solid #e7e4fa; }
li { padding:12px; margin:8px 0; border-radius:8px; background:#f7f8fc; } li.failed { background:#fff1f0; }
.trace-heading { display:flex; align-items:center; flex-wrap:wrap; gap:8px; font-size:12px; } time { margin-left:auto; color:#8993a4; }
code { color:#5946d8; } .trace-description { font-size:13px; line-height:1.7; margin-top:6px; }
.payload summary { font-size:11px; color:#718096; margin-top:8px; } pre { white-space:pre-wrap; overflow-wrap:anywhere; max-height:320px; overflow:auto; font:12px/1.7 Consolas,monospace; }
</style>
