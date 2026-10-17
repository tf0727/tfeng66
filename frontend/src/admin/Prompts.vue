<script setup lang="ts">
import { onMounted, ref } from 'vue'
const data = ref<any>({versions:[], proposals:[]}); const content=ref('')
onMounted(async()=> data.value=await (await fetch('http://localhost:8000/admin/prompts')).json())
async function save(){ await fetch('http://localhost:8000/admin/prompts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:content.value})}); data.value=await (await fetch('http://localhost:8000/admin/prompts')).json() }
async function optimize(){ await fetch('http://localhost:8000/admin/prompts/optimize',{method:'POST'}); data.value=await (await fetch('http://localhost:8000/admin/prompts')).json() }
async function approve(id:number){ await fetch(`/admin/prompts/proposals/${id}/approve`,{method:'POST'}); data.value=await (await fetch('http://localhost:8000/admin/prompts')).json() }
</script>
<template><main><h1>Prompt 管理</h1><textarea v-model="content" rows="16" cols="80" placeholder="请输入包含 ## 铁律 和 ## 语气 的 Prompt"/><br/><button @click="save">保存新版本</button><button @click="optimize">分析差评</button><h2>版本</h2><p v-for="v in data.versions" :key="v.version">v{{v.version}} · {{v.status}}</p><h2>待审核建议</h2><article v-for="p in data.proposals" :key="p.id"><pre>{{p.diff}}</pre><button v-if="p.status==='pending'" @click="approve(p.id)">批准</button></article></main></template>
