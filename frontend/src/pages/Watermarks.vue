<script setup>
import { onMounted, ref } from 'vue'
import { getJSON } from '../api'
const rows = ref([])
const err = ref('')
onMounted(async () => {
  try { rows.value = await getJSON('/api/watermarks') } catch (e) { err.value = String(e.message || e) }
})
</script>
<template>
  <div class="page">
    <h1>产出水位</h1>
    <p class="muted">各作业最近一次成功写出的水位时间与行数。</p>
    <p v-if="err" class="tag danger">{{ err }}</p>
    <div class="panel">
      <table>
        <thead><tr><th>作业</th><th>watermark</th><th>行数</th><th>更新</th></tr></thead>
        <tbody>
          <tr v-for="w in rows" :key="w.job_id">
            <td class="mono">{{ w.job_name }}</td>
            <td class="mono">{{ w.watermark_ts || '—' }}</td>
            <td>{{ w.artifact_rows }}</td>
            <td class="mono">{{ w.updated_at || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
