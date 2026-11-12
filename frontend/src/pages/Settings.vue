<script setup>
import { onMounted, ref } from 'vue'
import { getJSON } from '../api'
const rows = ref([])
const err = ref('')
onMounted(async () => {
  try { rows.value = await getJSON('/api/settings') } catch (e) { err.value = String(e.message || e) }
})
</script>
<template>
  <div class="page">
    <h1>设置</h1>
    <p class="muted">全局键值。SLA 等能力留给 0-1 切口。</p>
    <p v-if="err" class="tag danger">{{ err }}</p>
    <div class="panel">
      <table>
        <thead><tr><th>key</th><th>value</th></tr></thead>
        <tbody>
          <tr v-for="s in rows" :key="s.key">
            <td class="mono">{{ s.key }}</td>
            <td class="mono">{{ s.value }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
