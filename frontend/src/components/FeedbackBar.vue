<script setup lang="ts">
import { ref } from 'vue'
import { request, json } from '../api/client'
const props=defineProps<{sessionId:string,messageId?:number}>()
const comment=ref(''), status=ref(''), busy=ref(false)
async function submit(rating:string){
  if(!props.messageId)return
  busy.value=true
  try{await request('/admin/feedback',json('POST',{session_id:props.sessionId,message_id:props.messageId,rating,comment:comment.value}));status.value='已记录反馈'}catch(e){status.value=e instanceof Error?e.message:'反馈失败'}finally{busy.value=false}
}
</script>
<template><div class="feedback"><button :disabled="busy||!messageId" @click="submit('up')">👍</button><button :disabled="busy||!messageId" @click="submit('down')">👎</button><input v-model="comment" placeholder="可选反馈原因" aria-label="反馈原因" /><small>{{ status }}</small></div></template>
<style scoped>.feedback{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:6px}.feedback button{border:1px solid #ddd;border-radius:6px;background:#fff;cursor:pointer;padding:5px 9px}.feedback input{border:1px solid #e5e7eb;border-radius:6px;padding:6px;width:160px}.feedback small{color:#667085}button:disabled{opacity:.4}</style>
