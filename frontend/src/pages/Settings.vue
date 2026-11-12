<script setup>
import { onMounted, ref } from 'vue'
import { getJSON, putJSON } from '../api'
const rows = ref([])
const slots = ref(null)
const limit = ref(1)
const policy = ref('wait')
const msg = ref('')
const err = ref('')
async function refresh() {
  rows.value = await getJSON('/api/settings')
  slots.value = await getJSON('/api/settings/slots')
  limit.value = slots.value.concurrency_limit
  policy.value = slots.value.slot_policy
}
async function saveSlots() {
  err.value = ''; msg.value = ''
  try {
    await putJSON('/api/settings/slots', {
      concurrency_limit: Number(limit.value),
      slot_policy: policy.value,
    })
    msg.value = '已保存并发槽设置'
    await refresh()
  } catch (e) { err.value = String(e.message || e) }
}
onMounted(async () => {
  try { await refresh() } catch (e) { err.value = String(e.message || e) }
})
</script>
<template>
  <div class="page">
    <h1>设置</h1>
    <p class="muted">并发槽：层内同时执行的作业数上限，以及超限时的处置策略。</p>
    <p v-if="err" class="tag danger">{{ err }}</p>
    <p v-if="msg" class="tag ok">{{ msg }}</p>

    <div class="panel" v-if="slots">
      <h3>并发槽</h3>
      <div class="form-row">
        <label>
          层内并发上限
          <input
            type="number"
            :min="slots.min_concurrency_limit"
            :max="slots.max_concurrency_limit"
            v-model.number="limit"
            style="width:5rem"
          />
        </label>
        <label>
          超限处置
          <select v-model="policy">
            <option value="wait">wait — 排队等待槽位后执行</option>
            <option value="skip">skip — 记为 skipped_slot 跳过</option>
          </select>
        </label>
        <button @click="saveSlots">保存</button>
      </div>
      <p class="muted">
        范围 {{ slots.min_concurrency_limit }}–{{ slots.max_concurrency_limit }}，
        默认 {{ slots.default_concurrency_limit }} / {{ slots.default_slot_policy }}。
        wait 策略下超限作业记为 waited_then_acquired；skip 策略下记为 skipped_slot。
      </p>
    </div>

    <div class="panel">
      <h3>全部键值</h3>
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
