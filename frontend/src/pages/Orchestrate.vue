<script setup>
import { computed, onMounted, ref } from 'vue'
import { getJSON, postJSON } from '../api'
const history = ref([])
const last = ref(null)
const busy = ref(false)
const err = ref('')
const slots = ref(null)
const override = ref(false)
const limit = ref(1)
const policy = ref('wait')

const a11y = computed(() => {
  const r = last.value?.report
  if (!r) return null
  const listed = r.succeeded + r.failed + r.skipped
  return { listed, consistent: listed === r.attempt_count && r.attempt_count === r.job_total }
})

async function refresh() {
  history.value = await getJSON('/api/orchestrations')
  slots.value = await getJSON('/api/settings/slots')
  if (!override.value) {
    limit.value = slots.value.concurrency_limit
    policy.value = slots.value.slot_policy
  }
}
async function runOnce() {
  err.value = ''; busy.value = true
  try {
    const body = override.value
      ? { concurrency_limit: Number(limit.value), slot_policy: policy.value }
      : {}
    last.value = await postJSON('/api/orchestrations', body)
    await refresh()
  } catch (e) { err.value = String(e.message || e) }
  finally { busy.value = false }
}
onMounted(async () => {
  try { await refresh() } catch (e) { err.value = String(e.message || e) }
})
</script>
<template>
  <div class="page">
    <h1>编排台</h1>
    <p class="muted">触发一次全图编排：按依赖层执行，层内按并发槽上限取槽；超限作业按策略等待或跳过。</p>
    <p v-if="err" class="tag danger">{{ err }}</p>

    <div class="panel">
      <div class="form-row">
        <button :disabled="busy" @click="runOnce">{{ busy ? '编排中…' : '执行编排' }}</button>
        <label class="inline">
          <input type="checkbox" v-model="override" />
          本次覆盖槽位设置
        </label>
      </div>
      <div class="form-row" v-if="override && slots">
        <label>
          并发上限
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
            <option value="wait">wait</option>
            <option value="skip">skip</option>
          </select>
        </label>
      </div>
      <p class="muted" v-if="slots && !override">
        当前生效：limit={{ slots.concurrency_limit }} · policy={{ slots.slot_policy }}
        （<router-link to="/settings">去设置修改</router-link>）
      </p>
    </div>

    <div class="panel" v-if="last">
      <h3>最近一次报告</h3>
      <p>
        #{{ last.id }} · <span class="tag ok">{{ last.status }}</span> ·
        succeeded {{ last.report?.succeeded }} /
        failed {{ last.report?.failed }} /
        skipped {{ last.report?.skipped }}
        （dep {{ last.report?.skipped_dep }} · slot {{ last.report?.skipped_slot }}）/
        attempts {{ last.report?.attempt_count }}
      </p>
      <p class="mono muted">
        槽位 limit={{ last.report?.concurrency_limit }} policy={{ last.report?.slot_policy }}
        · waited_then_acquired={{ last.report?.waited_then_acquired }}
        · watermarked_jobs={{ last.report?.watermarked_jobs }} · layers={{ last.report?.layer_count }}
      </p>
      <p v-if="a11y">
        <span class="tag" :class="a11y.consistent ? 'ok' : 'danger'">
          {{ a11y.consistent
            ? `对账一致：${a11y.listed} = 尝试 ${last.report?.attempt_count} = 作业 ${last.report?.job_total}`
            : `对账不一致：列示 ${a11y.listed} / 尝试 ${last.report?.attempt_count} / 作业 ${last.report?.job_total}` }}
        </span>
      </p>
      <table v-if="last.report?.layers?.length">
        <thead><tr><th>层</th><th>作业</th><th>limit</th><th>策略</th><th>acquired</th><th>waited</th><th>skipped_slot</th><th>波次</th><th>峰值并发</th></tr></thead>
        <tbody>
          <tr v-for="l in last.report.layers" :key="l.layer">
            <td>{{ l.layer }}</td>
            <td>{{ l.job_total }}</td>
            <td>{{ l.slot_limit }}</td>
            <td>{{ l.slot_policy }}</td>
            <td>{{ l.dispositions.acquired }}</td>
            <td>{{ l.dispositions.waited_then_acquired }}</td>
            <td>{{ l.dispositions.skipped_slot }}</td>
            <td>{{ l.waves }}</td>
            <td>{{ l.peak_concurrency }}</td>
          </tr>
        </tbody>
      </table>
      <p>
        <router-link :to="{ path: '/attempts', query: { orchestration_id: last.id } }">查看本次尝试 →</router-link>
        ·
        <router-link to="/watermarks">产出水位 →</router-link>
      </p>
    </div>

    <div class="panel">
      <h3>历史编排</h3>
      <table>
        <thead><tr><th>ID</th><th>状态</th><th>成功</th><th>失败</th><th>跳过(dep)</th><th>槽位跳过</th><th>等待后成功</th><th>开始</th></tr></thead>
        <tbody>
          <tr v-for="o in history" :key="o.id">
            <td>{{ o.id }}</td>
            <td>{{ o.status }}</td>
            <td>{{ o.report?.succeeded }}</td>
            <td>{{ o.report?.failed }}</td>
            <td>{{ o.report?.skipped_dep }}</td>
            <td>{{ o.report?.skipped_slot }}</td>
            <td>{{ o.report?.waited_then_acquired }}</td>
            <td class="mono">{{ o.started_at }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
