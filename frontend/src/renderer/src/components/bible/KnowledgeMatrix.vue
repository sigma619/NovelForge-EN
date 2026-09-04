<template>
  <div class="knowledge-matrix">
    <el-empty v-if="!rows.length" :description="t('bible.empty.knowledgeHint')" :image-size="70" />
    <el-table v-else :data="rows" size="small" border stripe style="width: 100%" :scrollbar-always-on="true">
      <el-table-column :label="t('bible.knowledge.fact')" min-width="220" fixed>
        <template #default="{ row }">
          <div class="fact-cell">
            <span class="fact-text">{{ row.fact }}</span>
            <div class="fact-meta">
              <el-tag v-if="row.truth_status" size="small" effect="plain">{{ t('bible.truth.' + row.truth_status, row.truth_status) }}</el-tag>
              <el-tag v-if="row.sensitivity === 'high'" size="small" type="danger" effect="plain">high sensitivity</el-tag>
              <span v-if="row.planned_reveal_chapter != null" class="muted">{{ t('bible.knowledge.reveal') }} {{ row.planned_reveal_chapter }}</span>
              <el-button size="small" text type="primary" @click="emit('open-card', row.card_id)">{{ t('bible.openCard') }}</el-button>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column v-for="entity in entities" :key="entity" :label="entity === 'reader' ? t('bible.knowledge.reader') : entity" min-width="120" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.states[entity]" size="small" effect="dark" :type="stateType(row.states[entity])">{{ t('bible.knowledge.state.' + row.states[entity], row.states[entity]) }}</el-tag>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{ entities: string[]; rows: any[] }>()
const emit = defineEmits<{ (e: 'open-card', id: number): void }>()
const { t } = useI18n()

function stateType(s: string) {
  return s === 'knows' ? 'success' : s === 'suspects' ? 'warning' : s === 'false_belief' ? 'danger' : 'info'
}
</script>

<style scoped>
.knowledge-matrix { min-width: 0; width: 100%; overflow: hidden; }
.fact-cell { display: flex; flex-direction: column; gap: 4px; }
.fact-text { font-weight: 600; }
.fact-meta { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.muted { color: var(--el-text-color-secondary); font-size: 12px; }
</style>
