<template>
  <div class="relationship-matrix">
    <el-empty v-if="!arcs.length" :description="t('bible.empty.relationshipsHint')" :image-size="70" />
    <div v-else class="arc-grid">
      <el-card v-for="arc in arcs" :key="arc.card_id" shadow="never" class="arc-card">
        <template #header>
          <div class="arc-head">
            <span class="arc-title">{{ arc.character_a }} <span class="muted">↔</span> {{ arc.character_b }}</span>
            <el-tag v-if="arc.truth_status" size="small" effect="plain">{{ t('bible.truth.' + arc.truth_status, arc.truth_status) }}</el-tag>
            <el-button size="small" text type="primary" @click="emit('open-card', arc.card_id)">{{ t('bible.openCard') }}</el-button>
          </div>
        </template>
        <div class="dims">
          <div v-for="dim in dims" :key="dim" class="dim">
            <span class="dim-label">{{ t('bible.relationship.' + dim) }}</span>
            <el-progress :percentage="Number(arc[dim] ?? 0)" :stroke-width="8" :color="dimColor(dim)" :show-text="false" />
            <span class="dim-value">{{ arc[dim] ?? '-' }}</span>
          </div>
        </div>
        <div class="muted small" v-if="arc.public_relationship || arc.private_relationship">
          <div v-if="arc.public_relationship"><b>{{ t('bible.relationship.public') }}:</b> {{ arc.public_relationship }}</div>
          <div v-if="arc.private_relationship"><b>{{ t('bible.relationship.private') }}:</b> {{ arc.private_relationship }}</div>
        </div>
        <div v-if="milestoneTimeline(arc).length" class="timeline">
          <div class="value-label">{{ t('bible.relationship.milestones') }}</div>
          <el-timeline>
            <el-timeline-item v-for="(m, i) in milestoneTimeline(arc)" :key="i" :type="m.planned ? 'info' : 'primary'" :hollow="m.planned" size="small">
              <span class="muted small" v-if="m.chapter_number != null">Ch {{ m.chapter_number }} · </span>{{ m.event }}
              <span v-if="m.effect" class="muted small"> — {{ m.effect }}</span>
            </el-timeline-item>
          </el-timeline>
        </div>
        <div v-if="(arc.history || []).length" class="history">
          <div class="value-label">{{ t('bible.relationship.history') }}</div>
          <ul class="plain-list small">
            <li v-for="(h, i) in arc.history.slice(-6)" :key="i"><code>{{ h.field }}</code>: {{ pretty(h.previous) }} → {{ pretty(h.new) }}<span v-if="h.chapter_number != null" class="muted"> (ch {{ h.chapter_number }})</span></li>
          </ul>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const props = defineProps<{ arcs: any[] }>()
const emit = defineEmits<{ (e: 'open-card', id: number): void }>()
const { t } = useI18n()
const dims = ['trust', 'affection', 'fear', 'dependency', 'resentment'] as const

function dimColor(dim: string) {
  return { trust: '#67c23a', affection: '#e6a23c', fear: '#909399', dependency: '#409eff', resentment: '#f56c6c' }[dim] || '#409eff'
}
function milestoneTimeline(arc: any) {
  return [...(arc.milestones || [])].sort((a, b) => (a.chapter_number ?? 9999) - (b.chapter_number ?? 9999))
}
function pretty(v: unknown) { return typeof v === 'string' ? v : JSON.stringify(v) }
void props
</script>

<style scoped>
.arc-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; }
.arc-head { display: flex; align-items: center; gap: 8px; justify-content: space-between; }
.arc-title { font-weight: 600; }
.dims { display: flex; flex-direction: column; gap: 4px; margin-bottom: 8px; }
.dim { display: grid; grid-template-columns: 90px 1fr 32px; align-items: center; gap: 8px; font-size: 12px; }
.dim-label { color: var(--el-text-color-secondary); }
.dim-value { text-align: right; font-variant-numeric: tabular-nums; }
.muted { color: var(--el-text-color-secondary); }
.small { font-size: 12px; }
.value-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--el-text-color-secondary); margin: 8px 0 4px; }
.plain-list { margin: 0; padding-left: 16px; }
:deep(.el-timeline) { padding-left: 4px; }
:deep(.el-timeline-item) { padding-bottom: 8px; }
</style>
