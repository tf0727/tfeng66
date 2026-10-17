<script setup lang="ts">
import PageSwitcher from './components/PageSwitcher.vue'
import { onMounted, ref } from 'vue'
import FeedbackBar from './components/FeedbackBar.vue'
import ToolCallPanel from './components/ToolCallPanel.vue'
import { createSSEParser } from './api/sse'
import { API, request, json } from './api/client'

type ChatMessage={role:string,content:string,id?:number,request_id?:string}
const input=ref(''), sending=ref(false), tools=ref<{question:string,events:any[]}[]>([]), messages=ref<ChatMessage[]>([])
const sessionId=localStorage.getItem('consultant_session') || crypto.randomUUID()
localStorage.setItem('consultant_session',sessionId)
let activeRequest: {request_id:string,message:string}|null=null
let controller:AbortController|null=null
async function consume(job:{request_id:string,message:string},answerIndex:number) {
  let cursor=0, finished=false
  const turnIndex=tools.value.length
  tools.value.push({question:job.message,events:[]})
  for(let attempt=0;attempt<3 && !finished;attempt++){
    controller=new AbortController()
    let timer:ReturnType<typeof setTimeout>|undefined
    try {
      const reset=()=>{clearTimeout(timer);timer=setTimeout(()=>controller?.abort(),45000)}
      reset()
      const response=await fetch(API+'/chat',{...json('POST',{session_id:sessionId,...job,after_seq:cursor}),signal:controller.signal})
      if(!response.ok || !response.body)throw new Error('聊天请求失败：'+response.status)
      const parse=createSSEParser((name,data)=>{
        if(data.seq && data.seq<=cursor)return
        cursor=data.seq || cursor
        if(name==='delta')messages.value[answerIndex].content+=data.content || ''
        else tools.value[turnIndex].events.push({...data,event_type:name})
        if(name==='done'){
          finished=true
          messages.value[answerIndex].id=data.message_id
          sessionStorage.removeItem('consultant_active')
        }
      })
      const reader=response.body.getReader(), decoder=new TextDecoder()
      while(true){const {value,done}=await reader.read(); if(done){parse(decoder.decode());break} reset();parse(decoder.decode(value,{stream:true}))}
      if(!finished)throw new Error('流已中断')
    } catch(error){
      tools.value[turnIndex].events.push({event_type:'trace',stage:'reconnect',summary:attempt<2?'连接中断，使用相同请求号恢复事件，不重复生成。':'连接未恢复，请刷新页面继续恢复该请求。',timestamp:new Date().toISOString()})
      if(attempt<2)await new Promise(resolve=>setTimeout(resolve,1000))
    } finally {clearTimeout(timer)}
  }
  if(!finished && !messages.value[answerIndex].content) messages.value[answerIndex].content='连接中断，请刷新页面恢复请求。'
  if(finished && !messages.value[answerIndex].content) messages.value[answerIndex].content='本次请求已结束但没有正文，请发送新问题重试。'
}
async function send(){
  const text=input.value.trim()
  if(!text||sending.value)return
  input.value='';sending.value=true
  activeRequest={request_id:crypto.randomUUID(),message:text}
  sessionStorage.setItem('consultant_active',JSON.stringify(activeRequest))
  messages.value.push({role:'user',content:text,request_id:activeRequest.request_id},{role:'assistant',content:'',request_id:activeRequest.request_id})
  try {await consume(activeRequest,messages.value.length-1)} finally {sending.value=false;activeRequest=null}
}
async function stop(){
  if(activeRequest)await request('/chat/cancel',json('POST',{session_id:sessionId,request_id:activeRequest.request_id}))
}
function quick(text:string){input.value=text;send()}
onMounted(async()=>{
  try{
    const history=await request('/sessions/'+encodeURIComponent(sessionId))
    messages.value=history.messages
    const pending=sessionStorage.getItem('consultant_active')
    if(pending){
      const job=JSON.parse(pending)
      if(messages.value.some(m=>m.role==='assistant'&&m.request_id===job.request_id)){sessionStorage.removeItem('consultant_active');return}
      activeRequest=job;sending.value=true
      messages.value.push({role:'assistant',content:'',request_id:job.request_id})
      try{await consume(job,messages.value.length-1)}finally{sending.value=false;activeRequest=null}
    }
  }catch(error){tools.value.push({question:'会话恢复',events:[{event_type:'error',message:'历史读取失败，请确认服务已启动。'}]})}
})
</script>
<template><div class="app"><PageSwitcher destination="admin" /><aside><div class="brand"><b>⌁</b><strong>CodePath</strong><small>学习咨询助手</small></div><div class="online">● 咨询服务在线</div><nav><a class="active">⌂　在线咨询</a><a>▱　我的学习计划</a><a>♧　联系班主任</a></nav><footer>Powered by Qwen<br/><small>安全 · 专业 · 有温度</small></footer></aside><main><header><div><label>PROGRAMMING CONSULTANT</label><h1>编程学习咨询</h1></div><span>会话已保存 · {{sessionId.slice(0,8)}}</span></header><section class="chat"><div v-if="!messages.length" class="welcome"><i>✦</i><h2>你好，我来帮你规划编程学习路径</h2><p>无论是转行、提升，还是刚开始了解编程，都可以先和我聊聊。</p><div><button @click="quick('我想转行学编程，应该从哪里开始？')">我想转行学编程</button><button @click="quick('我想了解 Python 的学习路径')">了解 Python 学习路径</button></div></div><div v-else class="messages"><article v-for="(m,i) in messages" :key="i" :class="m.role"><em>{{m.role==='user'?'我':'✦'}}</em><div><small>{{m.role==='user'?'你':'咨询助手'}}</small><p>{{m.content}}<b v-if="sending&&i===messages.length-1">▌</b></p><FeedbackBar v-if="m.role==='assistant'&&m.content" :session-id="sessionId" :message-id="m.id" /></div></article></div><ToolCallPanel :tools="tools"/></section><footer class="composer"><form @submit.prevent="send"><input v-model="input" :disabled="sending" placeholder="说说你的学习目标，例如：我想转行学 Python"/><button :disabled="sending||!input.trim()">{{sending?'思考中…':'发送 ↑'}}</button><button v-if="sending" type="button" @click="stop">停止</button></form><small>AI 建议仅供参考，具体课程与班型可进一步联系班主任了解</small></footer></main></div></template>
<style>
*{box-sizing:border-box}body{margin:0;font-family:Inter,"Microsoft YaHei",sans-serif;background:#f5f7fb;color:#172033}.app{display:flex;min-height:100vh}aside{width:240px;background:#111827;color:#d7dce7;padding:28px 20px;display:flex;flex-direction:column}.brand{display:grid;grid-template-columns:35px 1fr;column-gap:10px;align-items:center;color:#fff;font-size:18px}.brand b{grid-row:span 2;background:#6d5dfc;border-radius:11px;width:35px;height:35px;text-align:center;padding-top:3px;font-size:25px}.brand small{font-size:11px;color:#8791a6}.online{margin-top:45px;padding:13px;background:#1d2737;border-radius:12px;font-size:12px;color:#6ee7b7}nav{margin-top:25px}nav a{display:block;padding:13px;border-radius:9px;color:#9da8ba;font-size:14px}nav .active{background:#6d5dfc;color:#fff}aside footer{margin-top:auto;color:#718096;font-size:11px;line-height:1.8}main{flex:1;display:flex;flex-direction:column;max-width:1100px;margin:auto;width:100%}header{padding:28px 6%;background:#fff;border-bottom:1px solid #e6e9f0;display:flex;justify-content:space-between;align-items:end}header label{font-size:10px;letter-spacing:2px;color:#887df7}h1{font-size:25px;margin:7px 0 0}header span{font-size:12px;color:#98a1b2}.chat{flex:1;padding:45px 12%;overflow:auto}.welcome{text-align:center;margin:8vh auto;max-width:580px}.welcome i{display:grid;place-items:center;margin:auto;width:55px;height:55px;border-radius:18px;background:#edeaff;color:#6d5dfc;font-size:28px;font-style:normal}.welcome h2{margin:20px 0 10px;font-size:24px}.welcome p{color:#8993a4;font-size:14px}.welcome button{border:1px solid #e0e3ec;background:#fff;border-radius:20px;padding:10px 15px;color:#5e6778;margin:12px 4px;cursor:pointer}.messages{display:flex;flex-direction:column;gap:24px}.messages article{display:flex;gap:12px;max-width:82%}.messages article.user{margin-left:auto;flex-direction:row-reverse}.messages em{width:32px;height:32px;border-radius:10px;background:#e9e7ff;color:#6d5dfc;display:grid;place-items:center;font-style:normal}.messages .user em{background:#dff5ee;color:#15916e}.messages small{color:#9aa3b3}.messages p{background:#fff;padding:13px 16px;border-radius:4px 15px 15px 15px;line-height:1.7;font-size:14px;white-space:pre-wrap;margin:6px 0}.messages .user p{background:#6d5dfc;color:#fff;border-radius:15px 4px 15px 15px}.composer{padding:18px 12% 24px;background:#fff;border-top:1px solid #e6e9f0}.composer form{display:flex;background:#f5f6fa;border:1px solid #e0e4ed;border-radius:14px;padding:6px}.composer input{flex:1;border:0;background:transparent;padding:12px;outline:0;font-size:14px}.composer button{border:0;border-radius:10px;background:#6d5dfc;color:#fff;padding:0 20px;cursor:pointer}.composer button:disabled{opacity:.5}.composer>small{display:block;text-align:center;color:#a1a8b5;font-size:10px;margin-top:9px}@media(max-width:700px){aside{display:none}header{padding:20px}.chat,.composer{padding-left:18px;padding-right:18px}header span{display:none}}
</style>
