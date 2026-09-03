<template>
  <div class="lab-wizard">
    <div class="lab-head">
      <h3 class="title">{{ t('bible.lab.title') }}</h3>
      <p class="muted">{{ t('bible.lab.subtitle') }}</p>
    </div>

    <el-steps :active="step" finish-status="success" align-center class="steps">
      <el-step :title="t('bible.lab.step1')" />
      <el-step :title="t('bible.lab.step2')" />
      <el-step :title="t('bible.lab.step3')" />
      <el-step :title="t('bible.lab.step4')" />
    </el-steps>

    <!-- Step 1: file + metadata -->
    <div v-show="step === 0" class="step-body">
      <label class="drop" :class="{ active: dragging }" @dragover.prevent="dragging = true" @dragleave="dragging = false" @drop.prevent="onDrop">
        <input ref="fileInput" type="file" accept=".txt,.md,.markdown,.epub,.docx" class="hidden-input" @change="onPick" />
        <div v-if="!file" class="drop-text">{{ t('bible.lab.dropFile') }}</div>
        <div v-else class="drop-text"><b>{{ file.name }}</b> · {{ (file.size / 1024).toFixed(0) }} KB</div>
      </label>
      <el-form label-position="top" size="small" class="meta-form">
        <div class="form-grid">
          <el-form-item :label="t('bible.lab.bookTitle')"><el-input v-model="meta.book_title" /></el-form-item>
          <el-form-item :label="t('bible.lab.author')"><el-input v-model="meta.author" /></el-form-item>
          <el-form-item :label="t('bible.lab.genre')"><el-input v-model="meta.genre" /></el-form-item>
          <el-form-item :label="t('bible.lab.language')"><el-input v-model="meta.language" /></el-form-item>
          <el-form-item :label="t('bible.lab.encoding')">
            <el-select v-model="detect.encoding" clearable :placeholder="t('bible.lab.autoDetect')">
              <el-option v-for="e in ['utf-8', 'utf-8-sig', 'utf-16', 'gb18030', 'cp1252', 'latin-1']" :key="e" :label="e" :value="e" />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('bible.lab.chapterPattern')">
            <el-select v-model="detect.chapter_pattern" clearable allow-create filterable default-first-option :placeholder="t('bible.lab.autoDetect')">
              <el-option v-for="p in patternCandidates" :key="p.name" :label="p.name" :value="p.pattern" />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('bible.lab.volumePattern')"><el-input v-model="detect.volume_pattern" :placeholder="t('bible.lab.autoDetect')" /></el-form-item>
        </div>
        <div class="switches">
          <el-checkbox v-model="detect.exclude_front_matter">{{ t('bible.lab.excludeFront') }}</el-checkbox>
          <el-checkbox v-model="detect.exclude_afterword">{{ t('bible.lab.excludeAfterword') }}</el-checkbox>
        </div>
      </el-form>
      <div class="actions">
        <el-button type="primary" :disabled="!file" :loading="previewing" @click="runPreview">{{ previewing ? t('bible.lab.previewing') : t('bible.lab.preview') }}</el-button>
      </div>
    </div>

    <!-- Step 2: chapter check & corrections -->
    <div v-show="step === 1" class="step-body">
      <div v-if="preview" class="summary">
        <el-alert type="info" :closable="false" show-icon :title="t('bible.lab.detected', { included: preview.included_chapters, total: preview.total_chapters, words: preview.total_words.toLocaleString(), volumes: preview.volumes.length, pattern: preview.pattern_name })" />
        <el-alert type="success" :closable="false" show-icon :title="t('bible.lab.estimate', { tokens: preview.estimated_input_tokens.toLocaleString(), chapters: preview.included_chapters })" />
        <el-alert v-if="preview.warnings.length" type="warning" :closable="false" show-icon :title="t('bible.lab.warnings')">
          <ul class="plain-list"><li v-for="(w, i) in preview.warnings" :key="i">{{ w }}</li></ul>
        </el-alert>
      </div>
      <el-table v-if="preview" :data="preview.chapters" size="small" border stripe max-height="420" :row-class-name="rowClass" style="width: 100%" :scrollbar-always-on="true">
        <el-table-column label="#" width="56" prop="index" />
        <el-table-column :label="t('common.title')" min-width="220">
          <template #default="{ row }">
            <div class="chapter-title">{{ row.title }}</div>
            <div class="muted preview-text">{{ row.preview }}</div>
          </template>
        </el-table-column>
        <el-table-column label="Vol" width="110" prop="volume" />
        <el-table-column label="Words" width="80" prop="word_count" align="right" />
        <el-table-column label="Flags" width="140">
          <template #default="{ row }">
            <el-tag v-for="f in row.flags" :key="f" size="small" :type="f === 'front_matter' || f === 'afterword' ? 'info' : 'warning'" effect="plain" class="flag">{{ t('bible.lab.flags.' + f, f) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('common.action')" width="120" fixed="right" align="center">
          <template #default="{ row }">
            <el-dropdown trigger="click" size="small" @command="(cmd: string) => rowAction(cmd, row)">
              <el-button size="small" text type="primary">{{ t('common.action') }} <el-icon><ArrowDown /></el-icon></el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item v-if="!isExcluded(row)" command="exclude">{{ t('bible.lab.actions.exclude') }}</el-dropdown-item>
                  <el-dropdown-item v-else command="include">{{ t('bible.lab.actions.include') }}</el-dropdown-item>
                  <el-dropdown-item command="merge">{{ t('bible.lab.actions.merge') }}</el-dropdown-item>
                  <el-dropdown-item command="rename">{{ t('bible.lab.actions.rename') }}</el-dropdown-item>
                  <el-dropdown-item command="split">{{ t('bible.lab.actions.split') }}</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>
      <div class="actions">
        <el-button @click="step = 0">{{ t('common.back') }}</el-button>
        <el-checkbox v-model="replaceExisting" class="replace">{{ t('bible.lab.replaceExisting') }}</el-checkbox>
        <el-button type="primary" :disabled="!preview || !projectId" :loading="importing" @click="runImport">
          {{ importing ? t('bible.lab.importing') : t('bible.lab.import', { n: preview?.included_chapters || 0 }) }}
        </el-button>
      </div>
    </div>

    <!-- Step 3 / 4: manuscript status + workflow hand-off -->
    <div v-show="step >= 2" class="step-body">
      <el-alert v-if="importResult" type="success" :closable="false" show-icon :title="t('bible.lab.imported', { n: importResult.chapter_count, words: importResult.total_words.toLocaleString() })" />
      <el-alert type="info" :closable="false" show-icon :title="t('bible.lab.runWorkflowHint')" />
      <div class="actions">
        <el-button @click="step = 1" :disabled="!preview">{{ t('common.back') }}</el-button>
        <el-button type="primary" @click="openWorkflow">{{ t('bible.lab.runWorkflow') }}</el-button>
      </div>
      <p class="muted">{{ t('bible.lab.legacy') }}</p>
      <p class="muted">{{ t('bible.lab.genomeHint') }}</p>
    </div>

    <el-divider />
    <div class="manuscript">
      <div class="manuscript-head">
        <h4 class="subtitle">{{ t('bible.lab.manuscript') }}</h4>
        <el-button size="small" @click="loadManuscript">{{ t('bible.refresh') }}</el-button>
      </div>
      <el-empty v-if="!manuscript?.chapters?.length" :description="t('bible.lab.noManuscript')" :image-size="60" />
      <template v-else>
        <div class="muted">{{ manuscript.meta.book_title }}<span v-if="manuscript.meta.author"> · {{ manuscript.meta.author }}</span> · {{ manuscript.chapters.length }} chapters · {{ analysedCount }} analysed</div>
        <el-progress :percentage="manuscript.chapters.length ? Math.round(100 * analysedCount / manuscript.chapters.length) : 0" :stroke-width="10" />
        <el-table :data="manuscript.chapters" size="small" border max-height="260" class="manuscript-table" style="width: 100%" :scrollbar-always-on="true">
          <el-table-column label="#" width="56" prop="chapter_number" />
          <el-table-column :label="t('common.title')" min-width="200" prop="title" />
          <el-table-column label="Vol" width="120" prop="volume" />
          <el-table-column label="Words" width="80" prop="word_count" align="right" />
          <el-table-column :label="t('bible.lab.analysisStatus')" width="120">
            <template #default="{ row }"><el-tag size="small" :type="row.analysis_status === 'done' ? 'success' : 'info'" effect="plain">{{ row.analysis_status }}</el-tag></template>
          </el-table-column>
          <el-table-column label="Scenes" width="80" prop="scene_count" align="right" />
          <el-table-column width="110">
            <template #default="{ row }"><el-button size="small" text type="primary" @click="emit('open-card', row.card_id)">{{ t('bible.openCard') }}</el-button></template>
          </el-table-column>
        </el-table>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import { useAppStore } from '@renderer/stores/useAppStore'
import {
  fileToBase64,
  getManuscriptDefaults,
  importManuscript,
  listManuscript,
  previewManuscript,
  type ChapterPreview,
  type ManuscriptImportResponse,
  type ManuscriptListResponse,
  type ManuscriptPreviewResponse,
} from '@renderer/api/lab'

const props = defineProps<{ projectId?: number }>()
const emit = defineEmits<{ (e: 'open-card', id: number): void; (e: 'imported'): void }>()
const { t } = useI18n()
const appStore = useAppStore()

const step = ref(0)
const file = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const dragging = ref(false)
const previewing = ref(false)
const importing = ref(false)
const replaceExisting = ref(true)
const contentBase64 = ref('')
const preview = ref<ManuscriptPreviewResponse | null>(null)
const importResult = ref<ManuscriptImportResponse | null>(null)
const manuscript = ref<ManuscriptListResponse | null>(null)
const patternCandidates = ref<Array<{ name: string; pattern: string }>>([])
const corrections = ref<Array<Record<string, unknown>>>([])

const meta = reactive({ book_title: '', author: '', genre: '', language: '' })
const detect = reactive({ encoding: '' as string | undefined, chapter_pattern: '' as string | undefined, volume_pattern: '' as string | undefined, exclude_front_matter: true, exclude_afterword: true })

const analysedCount = computed(() => (manuscript.value?.chapters || []).filter((c: any) => c.analysis_status === 'done').length)

function onPick(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (f) setFile(f)
}
function onDrop(e: DragEvent) {
  dragging.value = false
  const f = e.dataTransfer?.files?.[0]
  if (f) setFile(f)
}
async function setFile(f: File) {
  file.value = f
  contentBase64.value = await fileToBase64(f)
  if (!meta.book_title) meta.book_title = f.name.replace(/\.[^.]+$/, '')
  corrections.value = []
  preview.value = null
}

function payload() {
  return {
    filename: file.value?.name || 'manuscript.txt',
    content_base64: contentBase64.value,
    encoding: detect.encoding || null,
    chapter_pattern: detect.chapter_pattern || null,
    volume_pattern: detect.volume_pattern || null,
    exclude_front_matter: detect.exclude_front_matter,
    exclude_afterword: detect.exclude_afterword,
    corrections: corrections.value as any,
    preview_chars: 220,
  }
}

async function runPreview() {
  if (!file.value) return
  previewing.value = true
  try {
    preview.value = await previewManuscript(payload())
    step.value = 1
  } catch (e) { console.error(e) } finally { previewing.value = false }
}

async function correct(op: Record<string, unknown>) {
  corrections.value.push(op)
  previewing.value = true
  try { preview.value = await previewManuscript(payload()) } finally { previewing.value = false }
}
async function rename(row: ChapterPreview) {
  try {
    const { value } = await ElMessageBox.prompt(t('bible.lab.actions.rename'), row.title, { inputValue: row.title })
    if (value && value !== row.title) await correct({ op: 'rename', index: row.index, title: value })
  } catch { /* cancelled */ }
}
async function split(row: ChapterPreview) {
  try {
    const { value } = await ElMessageBox.prompt(t('bible.lab.splitPrompt'), row.title)
    if (value) await correct({ op: 'split', index: row.index, at_text: value })
  } catch { /* cancelled */ }
}
function isExcluded(row: ChapterPreview) { return row.flags.includes('front_matter') || row.flags.includes('afterword') }
function rowAction(cmd: string, row: ChapterPreview) {
  if (cmd === 'exclude' || cmd === 'include') void correct({ op: cmd, index: row.index })
  else if (cmd === 'merge') void correct({ op: 'merge_with_next', index: row.index })
  else if (cmd === 'rename') void rename(row)
  else if (cmd === 'split') void split(row)
}
function rowClass({ row }: { row: ChapterPreview }) { return isExcluded(row) ? 'row-excluded' : '' }

async function runImport() {
  if (!props.projectId || !preview.value) return
  importing.value = true
  try {
    importResult.value = await importManuscript({ ...payload(), project_id: props.projectId, ...meta, replace_existing: replaceExisting.value } as any)
    step.value = 2
    ElMessage.success(t('bible.lab.imported', { n: importResult.value.chapter_count, words: importResult.value.total_words.toLocaleString() }))
    await loadManuscript()
    emit('imported')
  } catch (e) { console.error(e); ElMessage.error(t('bible.lab.importFailed')) } finally { importing.value = false }
}

async function loadManuscript() {
  if (!props.projectId) { manuscript.value = null; return }
  try {
    manuscript.value = await listManuscript(props.projectId)
    if (manuscript.value?.chapters?.length && step.value < 2 && !file.value) step.value = 2
  } catch (e) { console.error(e) }
}

function openWorkflow() {
  appStore.goToWorkflows()
  window.location.hash = '#/workflows'
}

watch(() => props.projectId, loadManuscript)
onMounted(async () => {
  try { const d = await getManuscriptDefaults(); patternCandidates.value = d.pattern_candidates } catch { /* ignore */ }
  await loadManuscript()
})
</script>

<style scoped>
.lab-wizard { display: flex; flex-direction: column; gap: 12px; }
.title { margin: 0; font-size: 16px; }
.subtitle { margin: 0; font-size: 14px; }
.muted { color: var(--el-text-color-secondary); font-size: 12px; margin: 0; }
.steps { margin: 4px 0; }
.steps :deep(.el-step__title) { font-size: 12px; line-height: 1.3; word-break: normal; }
.step-body { display: flex; flex-direction: column; gap: 10px; }
.drop { display: flex; align-items: center; justify-content: center; min-height: 96px; border: 2px dashed var(--el-border-color); border-radius: 10px; cursor: pointer; background: var(--el-fill-color-lighter); transition: border-color .15s; }
.drop.active, .drop:hover { border-color: var(--el-color-primary); }
.drop-text { padding: 12px; text-align: center; }
.hidden-input { display: none; }
.form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0 12px; }
.switches { display: flex; gap: 16px; }
.actions { display: flex; gap: 8px; align-items: center; justify-content: flex-end; flex-wrap: wrap; }
.replace { margin-right: auto; white-space: normal; }
.replace :deep(.el-checkbox__label) { white-space: normal; line-height: 1.3; }
.summary { display: flex; flex-direction: column; gap: 6px; }
.plain-list { margin: 4px 0 0; padding-left: 16px; }
.chapter-title { font-weight: 600; }
.preview-text { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 520px; }
.flag { margin-right: 4px; }
:deep(.row-excluded) { opacity: 0.55; }
.manuscript { display: flex; flex-direction: column; gap: 8px; }
.manuscript-head { display: flex; justify-content: space-between; align-items: center; }
.manuscript-table { margin-top: 4px; }
</style>
