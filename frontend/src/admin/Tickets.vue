<script setup lang="ts">
import { onMounted, ref } from 'vue'
const tickets = ref<any[]>([])
onMounted(async()=> tickets.value = await (await fetch('http://localhost:8000/admin/tickets')).json())
async function resolve(t:any){ await fetch(`http://localhost:8000/admin/tickets/${t.id}?status=resolved`,{method:'PATCH'}); t.status='resolved' }
</script>
<template><main><h1>工单管理</h1><article v-for="t in tickets" :key="t.id"><b>{{t.id}}</b> {{t.reason}} · {{t.status}}<p>{{t.summary}}</p><button v-if="t.status!=='resolved'" @click="resolve(t)">标记已处理</button></article></main></template>
