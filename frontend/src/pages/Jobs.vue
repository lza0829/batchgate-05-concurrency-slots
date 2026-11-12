<script setup>
import { onMounted, ref } from 'vue'
import { getJSON, patchJSON } from '../api'
const rows = ref([])
const msg = ref('')
const err = ref('')
async function refresh() { rows.value = await getJSON('/api/jobs') }
async function saveAttempts(row) {
  err.value = ''; msg.value = ''
  try {
    await patchJSON(`/api/jobs/${row.id}/max-attempts`, { max_attempts: Number(row.max_attempts) || 1 })
    msg.value = `已保存 ${row.name} 的 max_attempts`
    await refresh()
  } catch (e) { err.value = String(e.message || e) }
}
onMounted(async () => {
  try { await refresh() } catch (e) { err.value = String(e.message || e) }
})
</script>
<template>
  <div class="page">
    <h1>作业</h1>
    <p class="muted">查看依赖与单次最大尝试次数。底座执行时仍只跑 1 次；重试预算留给 0-1 题。</p>
    <p v-if="err" class="tag danger">{{ err }}</p>
    <p v-if="msg" class="tag ok">{{ msg }}</p>
    <div class="panel">
      <table>
        <thead><tr><th>ID</th><th>名称</th><th>依赖</th><th>max_attempts</th><th>夹具</th><th></th></tr></thead>
        <tbody>
          <tr v-for="j in rows" :key="j.id">
            <td>{{ j.id }}</td>
            <td class="mono">{{ j.name }}</td>
            <td class="mono">{{ j.depends_on.join(', ') || '—' }}</td>
            <td><input type="number" min="1" max="10" v-model.number="j.max_attempts" style="width:4.5rem" /></td>
            <td class="mono">{{ j.fixture_path }}</td>
            <td><button class="secondary" @click="saveAttempts(j)">保存</button></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
