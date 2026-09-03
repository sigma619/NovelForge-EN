<template>
  <div class="bible-update-review">
    <template v-if="!selected">
      <div class="review-head">
        <div>
          <h3 class="title">{{ t('bible.updates.title') }}</h3>
          <p class="muted">{{ t('bible.updates.subtitle') }}</p>
        </div>
        <el-button size="small" :loading="loading" @click="load">{{ t('bible.refresh') }}</el-button>
      </div>
      <el-empty v-if="!loading && reviews.length === 0" :description="t('bible.empty.updatesHint')" :image-size="70" />
      <div v-else class="review-list" v-loading="loading">
        <div v-for="r in reviews" :key="r.id" class="review-item">
          <div class="review-item-main">
            <div class="review-item-title">
              {{ t('bible.updates.chapter', { n: r.chapter_number ?? '?' }) }}
              <el-tag size="small" :type="statusType(r.status)" effect="plain">{{ t('bible.updates.' + r.status, r.status) }}</el-tag>
            </div>
            <div class="muted">{{ t('bible.updates.changes', { n: r.proposal.changes?.length || 0 }) }} · {{ formatTime(r.created_at) }}</div>
          </div>
          <div class="review-item-actions">
            <el-button size="small" type="primary" plain @click="open(r)">{{ t('bible.updates.open') }}</el-button>
            <el-popconfirm :title="t('misc.confirmDeleteShort')" @confirm="dismiss(r)">
              <template #reference>
                <el-button size="small" type="danger" plain>{{ t('bible.updates.dismiss') }}</el-button>
              </template>
            </el-popconfirm>
          </div>
        </div>
      </div>
    </template>

    <template v-else>
      <div class="review-head">
        <div class="head-left">
          <el-button size="small" @click="selected = null">{{ t('common.back') }}</el-button>
          <h3 class="title inline">{{ t('bible.updates.chapter', { n: selected.chapter_number ?? '?' }) }}</h3>
          <el-tag size="small" :type="statusType(selected.status)" effect="plain">{{ t('bible.updates.' + selected.status, selected.status) }}</el-tag>
        </div>
        <div class="head-actions">
          <el-button size="small" @click="bulk('accept', true)">{{ t('bible.updates.acceptLowRisk') }}</el-button>
          <el-button size="small" @click="bulk('accept')">{{ t('bible.updates.acceptAll') }}</el-button>
          <el-button size="small" @click="bulk('reject')">{{ t('bible.updates.rejectAll') }}</el-button>
          <el-button size="small" type="primary" :loading="applying" :disabled="pendingCount === 0" @click="apply">
            {{ t('bible.updates.apply') }} ({{ pendingCount }})
          </el-button>
        </div>
      </div>

      <el-collapse v-if="selected.proposal.extraction_thinking || selected.proposal.unplanned_events?.length || selected.proposal.planned_but_missing?.length" class="meta-collapse">
        <el-collapse-item v-if="selected.proposal.extraction_thinking" :title="t('bible.updates.thinking')">
          <p class="muted pre">{{ selected.proposal.extraction_thinking }}</p>
        </el-collapse-item>
        <el-collapse-item v-if="selected.proposal.planned_but_missing?.length" :title="t('bible.updates.missing')">
          <ul class="plain-list"><li v-for="(m, i) in selected.proposal.planned_but_missing" :key="i">{{ m }}</li></ul>
        </el-collapse-item>
        <el-collapse-item v-if="selected.proposal.unplanned_events?.length" :title="t('bible.updates.unplanned')">
          <ul class="plain-list"><li v-for="(m, i) in selected.proposal.unplanned_events" :key="i">{{ m }}</li></ul>
        </el-collapse-item>
      </el-collapse>

      <div class="changes">
        <div v-for="c in selected.proposal.changes || []" :key="c.id" class="change" :class="[`risk-${c.risk}`, { decided: isDecided(c.id) }]">
          <div class="change-head">
            <span class="change-glyph">{{ glyph(c.kind) }}</span>
            <el-tag size="small" effect="dark" :type="kindType(c.kind)">{{ t('bible.updates.kind.' + c.kind, c.kind) }}</el-tag>
            <span class="change-summary">{{ c.summary }}</span>
          </div>
          <div class="change-meta muted">
            <span v-if="c.target_card_type !== 'none'">{{ t('bible.updates.target') }}: {{ c.target_card_type }}<template v-if="c.target_title"> · {{ c.target_title }}</template><template v-if="c.field_path"> · <code>{{ c.field_path }}</code></template></span>
            <el-tag size="small" effect="plain">{{ t('bible.truth.' + c.truth_status, c.truth_status) }}</el-tag>
            <el-tag size="small" effect="plain" :type="c.explicit ? 'success' : 'warning'">{{ c.explicit ? t('bible.updates.explicit') : t('bible.updates.inferred') }}</el-tag>
            <el-tag size="small" effect="plain" :type="riskType(c.risk)">{{ c.risk }} {{ t('bible.updates.risk') }}</el-tag>
            <span>{{ t('bible.updates.confidence') }} {{ Math.round((c.confidence ?? 0) * 100) }}%</span>
          </div>
          <div class="change-values">
            <div v-if="c.previous_value !== null && c.previous_value !== undefined" class="value-block">
              <div class="value-label">{{ t('bible.updates.previous') }}</div>
              <pre class="value">{{ pretty(c.previous_value) }}</pre>
            </div>
            <div class="value-block">
              <div class="value-label">{{ t('bible.updates.proposed') }}</div>
              <pre class="value">{{ pretty(editedValue(c.id) ?? c.new_value) }}</pre>
            </div>
          </div>
          <div v-if="c.evidence?.length" class="evidence">
            <div class="value-label">{{ t('bible.updates.evidence') }}</div>
            <ul class="plain-list">
              <li v-for="(e, i) in c.evidence" :key="i">
                <el-tag v-if="e.chapter_number != null" size="small" type="info" effect="plain">Ch {{ e.chapter_number }}</el-tag>
                <span v-if="e.scene" class="muted"> {{ e.scene }} </span>
                <q v-if="e.quote">{{ e.quote }}</q>
                <span v-if="e.note" class="muted"> — {{ e.note }}</span>
              </li>
            </ul>
          </div>
          <div v-if="c.conflicting_evidence?.length" class="evidence conflicting">
            <div class="value-label">{{ t('bible.updates.conflicting') }}</div>
            <ul class="plain-list"><li v-for="(e, i) in c.conflicting_evidence" :key="i"><el-tag v-if="e.chapter_number != null" size="small" type="danger" effect="plain">Ch {{ e.chapter_number }}</el-tag> <q v-if="e.quote">{{ e.quote }}</q></li></ul>
          </div>
          <p v-if="c.note" class="muted">{{ c.note }}</p>
          <div class="change-actions">
            <template v-if="isDecided(c.id)">
              <el-tag size="small" type="success" effect="dark">{{ t('bible.updates.decision.' + decisionAction(c.id), decisionAction(c.id)) }}</el-tag>
            </template>
            <template v-else>
              <el-radio-group v-model="decisions[c.id]" size="small">
                <el-radio-button value="accept">{{ t('bible.updates.decision.accept') }}</el-radio-button>
                <el-radio-button value="reject">{{ t('bible.updates.decision.reject') }}</el-radio-button>
                <el-radio-button value="postpone">{{ t('bible.updates.decision.postpone') }}</el-radio-button>
                <el-radio-button value="mark_planned">{{ t('bible.updates.decision.mark_planned') }}</el-radio-button>
                <el-radio-button v-if="c.kind === 'contradiction'" value="intentional_contradiction">{{ t('bible.updates.decision.intentional_contradiction') }}</el-radio-button>
                <el-radio-button v-if="c.kind === 'contradiction' || c.truth_status === 'believed'" value="unreliable_narration">{{ t('bible.updates.decision.unreliable_narration') }}</el-radio-button>
              </el-radio-group>
              <el-button size="small" text type="primary" @click="startEdit(c)">{{ t('bible.updates.decision.edit') }}</el-button>
            </template>
          </div>
        </div>
      </div>
    </template>

    <el-dialog v-model="editDialog.visible" :title="t('bible.updates.editValue')" width="560px">
      <el-input v-model="editDialog.text" type="textarea" :autosize="{ minRows: 4, maxRows: 16 }" />
      <template #footer>
        <el-button @click="editDialog.visible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="confirmEdit">{{ t('common.confirm') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import {
  decideBibleUpdate,
  deleteBibleUpdate,
  getBibleUpdate,
  listBibleUpdates,
  type BibleUpdateReviewRead,
  type ChangeDecision,
  type DecisionAction,
  type ProposedChange,
} from '@renderer/api/bible'

const props = defineProps<{ projectId?: number; openReviewId?: number | null }>()
const emit = defineEmits<{ (e: 'applied'): void }>()
const { t } = useI18n()

const loading = ref(false)
const applying = ref(false)
const reviews = ref<BibleUpdateReviewRead[]>([])
const selected = ref<BibleUpdateReviewRead | null>(null)
const decisions = reactive<Record<string, DecisionAction | undefined>>({})
const edits = reactive<Record<string, unknown>>({})
const editDialog = reactive({ visible: false, changeId: '', text: '' })

const pendingCount = computed(() => Object.values(decisions).filter(Boolean).length)

async function load() {
  if (!props.projectId) { reviews.value = []; return }
  loading.value = true
  try {
    const res = await listBibleUpdates(props.projectId)
    reviews.value = (res.items || []).filter(r => r.status !== 'applied' || (r.proposal.changes || []).some(c => !r.decisions[c.id]))
  } catch (e) { console.error(e) } finally { loading.value = false }
}

async function open(r: BibleUpdateReviewRead) {
  Object.keys(decisions).forEach(k => delete decisions[k])
  Object.keys(edits).forEach(k => delete edits[k])
  selected.value = r
}

async function dismiss(r: BibleUpdateReviewRead) {
  await deleteBibleUpdate(r.id)
  await load()
}

function decisionRecord(id: string): { action?: string } | undefined {
  return (selected.value?.decisions as Record<string, { action?: string }> | undefined)?.[id]
}

function decisionAction(id: string): string {
  return decisionRecord(id)?.action || ''
}

function isDecided(id: string): boolean {
  const action = decisionAction(id)
  return !!action && action !== 'postpone'
}

function editedValue(id: string) { return edits[id] }

function bulk(action: DecisionAction, lowRiskOnly = false) {
  for (const c of selected.value?.proposal.changes || []) {
    if (isDecided(c.id)) continue
    if (lowRiskOnly && c.risk !== 'low') continue
    decisions[c.id] = action
  }
}

function startEdit(c: ProposedChange) {
  editDialog.changeId = c.id
  const v = edits[c.id] ?? c.new_value
  editDialog.text = typeof v === 'string' ? v : JSON.stringify(v, null, 2)
  editDialog.visible = true
}

function confirmEdit() {
  const raw = editDialog.text
  let value: unknown = raw
  try { value = JSON.parse(raw) } catch { /* keep as text */ }
  edits[editDialog.changeId] = value
  if (!decisions[editDialog.changeId]) decisions[editDialog.changeId] = 'accept'
  editDialog.visible = false
}

async function apply() {
  if (!selected.value) return
  const payload: ChangeDecision[] = Object.entries(decisions)
    .filter(([, a]) => !!a)
    .map(([change_id, action]) => ({ change_id, action: action as DecisionAction, edited_value: edits[change_id] ?? null }))
  if (!payload.length) { ElMessage.info(t('bible.updates.noPending')); return }
  applying.value = true
  try {
    const res = await decideBibleUpdate(selected.value.id, { decisions: payload })
    ElMessage.success(t('bible.updates.applied', { applied: res.applied, rejected: res.rejected, postponed: res.postponed }))
    if (res.errors?.length) ElMessage.warning(`${t('bible.updates.errors')}: ${res.errors.slice(0, 3).join(' | ')}`)
    selected.value = await getBibleUpdate(selected.value.id)
    Object.keys(decisions).forEach(k => delete decisions[k])
    emit('applied')
    await load()
  } catch (e) { console.error(e) } finally { applying.value = false }
}

function statusType(s: string) { return s === 'applied' ? 'success' : s === 'partially_applied' ? 'warning' : 'info' }
function riskType(r: string) { return r === 'high' ? 'danger' : r === 'medium' ? 'warning' : 'success' }
function kindType(k: string) {
  if (k === 'contradiction') return 'danger'
  if (k === 'plan_deviation' || k === 'style_drift') return 'warning'
  if (k === 'payoff_delivered' || k === 'thread_resolved') return 'success'
  return 'primary'
}
function glyph(k: string) {
  if (k === 'contradiction') return '!'
  if (k === 'payoff_delivered' || k === 'thread_resolved') return '✓'
  if (k === 'plan_deviation' || k === 'relationship_change' || k === 'goal_change' || k === 'belief_change' || k === 'character_state') return '~'
  return '+'
}
function pretty(v: unknown): string {
  if (v === null || v === undefined) return ''
  if (typeof v === 'string') return v
  try { return JSON.stringify(v, null, 2) } catch { return String(v) }
}
function formatTime(v: string) { try { return new Date(v).toLocaleString() } catch { return v } }

watch(() => props.projectId, load)
watch(() => props.openReviewId, async (id) => {
  if (!id) return
  try { await open(await getBibleUpdate(id)) } catch (e) { console.error(e) }
})
onMounted(async () => {
  await load()
  if (props.openReviewId) { try { await open(await getBibleUpdate(props.openReviewId)) } catch { /* ignore */ } }
})
defineExpose({ load })
</script>

<style scoped>
.bible-update-review { display: flex; flex-direction: column; gap: 12px; }
.review-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; flex-wrap: wrap; }
.head-left { display: flex; align-items: center; gap: 10px; }
.head-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.title { margin: 0; font-size: 16px; }
.title.inline { display: inline; }
.muted { color: var(--el-text-color-secondary); font-size: 12px; margin: 0; }
.pre { white-space: pre-wrap; }
.review-list { display: flex; flex-direction: column; gap: 8px; }
.review-item { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 10px 12px; border: 1px solid var(--el-border-color-lighter); border-radius: 8px; background: var(--el-fill-color-blank); }
.review-item-title { font-weight: 600; display: flex; gap: 8px; align-items: center; }
.review-item-actions { display: flex; gap: 6px; }
.changes { display: flex; flex-direction: column; gap: 10px; }
.change { border: 1px solid var(--el-border-color-lighter); border-left-width: 4px; border-radius: 8px; padding: 10px 12px; background: var(--el-fill-color-blank); display: flex; flex-direction: column; gap: 6px; }
.change.risk-low { border-left-color: var(--el-color-success); }
.change.risk-medium { border-left-color: var(--el-color-warning); }
.change.risk-high { border-left-color: var(--el-color-danger); }
.change.decided { opacity: 0.7; }
.change-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.change-glyph { font-family: monospace; font-weight: 700; width: 14px; text-align: center; }
.change-summary { font-weight: 600; flex: 1 1 100%; min-width: 0; line-height: 1.4; }
.change-meta { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.change-values { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 8px; }
.value-block { min-width: 0; }
.value-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--el-text-color-secondary); margin-bottom: 2px; }
.value { margin: 0; padding: 6px 8px; background: var(--el-fill-color-light); border-radius: 6px; font-size: 12px; white-space: pre-wrap; word-break: break-word; max-height: 220px; overflow: auto; }
.evidence q { font-style: italic; }
.evidence.conflicting { border-top: 1px dashed var(--el-color-danger-light-5); padding-top: 4px; }
.plain-list { margin: 0; padding-left: 18px; font-size: 12px; }
.change-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.meta-collapse { border-radius: 8px; }
</style>
