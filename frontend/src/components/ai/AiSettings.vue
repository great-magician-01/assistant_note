<script setup lang="ts">
import { ref, watch } from 'vue'
import Icon from '@/components/Icon.vue'
import AiModelFormModal from './AiModelFormModal.vue'
import AiConfigFormModal from './AiConfigFormModal.vue'
import { useAiStore } from '@/stores/ai'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import { extractErrorMessage } from '@/api/client'
import type { AiConfig, AiModel } from '@/types'

const props = defineProps<{
  /** Whether the settings panel is the active view. Used to lazy-load data. */
  visible: boolean
}>()

const aiStore = useAiStore()
const authStore = useAuthStore()
const toast = useToast()

type Tab = 'models' | 'configs' | 'tools'
const tab = ref<Tab>('models')

const modelModalVisible = ref(false)
const editingModel = ref<AiModel | null>(null)
const configModalVisible = ref(false)
const editingConfig = ref<AiConfig | null>(null)

// Lazy-load: the whole page is admin-only (the tools endpoint 403s for
// non-admins), and there's no point fetching until the user actually opens it.
let loaded = false
async function ensureLoaded() {
  if (loaded || !authStore.isAdmin) return
  loaded = true
  try {
    await aiStore.fetchAll()
  } catch (err) {
    toast.error(extractErrorMessage(err, '加载 AI 配置失败'))
  }
}
watch(
  () => props.visible,
  (v) => {
    if (v) void ensureLoaded()
  },
  { immediate: true },
)

function openCreateModel() {
  editingModel.value = null
  modelModalVisible.value = true
}
function openEditModel(m: AiModel) {
  editingModel.value = m
  modelModalVisible.value = true
}
async function onDeleteModel(m: AiModel) {
  if (!window.confirm(`确定删除模型「${m.name}」？`)) return
  try {
    await aiStore.removeModel(m.model_id)
    toast.success('已删除模型')
  } catch (err) {
    toast.error(extractErrorMessage(err, '删除失败'))
  }
}

function openCreateConfig() {
  if (!aiStore.models.length) {
    toast.error('请先在「模型池」中添加模型')
    return
  }
  editingConfig.value = null
  configModalVisible.value = true
}
function openEditConfig(c: AiConfig) {
  editingConfig.value = c
  configModalVisible.value = true
}
async function onDeleteConfig(c: AiConfig) {
  if (!window.confirm(`确定删除配置「${c.config_name}」？`)) return
  try {
    await aiStore.removeConfig(c.config_id)
    toast.success('已删除配置')
  } catch (err) {
    toast.error(extractErrorMessage(err, '删除失败'))
  }
}

/** Show api_key masked in the list (abc***xyz) for at-a-glance safety. */
function maskKey(key: string): string {
  if (!key) return ''
  if (key.length <= 8) return '***'
  return `${key.slice(0, 3)}***${key.slice(-4)}`
}

function toolsLabel(c: AiConfig): string {
  const t = c.tools ?? []
  if (!t.length) return '—'
  return t.join(', ')
}

function paramLabel(v: number | null): string {
  return v === null || v === undefined ? '默认' : String(v)
}
</script>

<template>
  <div class="settings-view">
    <div class="settings-header">
      <div class="title-area">
        <div class="title-icon">
          <Icon name="settings" :size="20" />
        </div>
        <div>
          <div class="title">AI 配置管理</div>
          <div class="subtitle">管理模型池、运行配置与工具注册表（管理员）</div>
        </div>
      </div>
    </div>

    <div class="tabs">
      <button
        class="tab"
        :class="{ active: tab === 'models' }"
        @click="tab = 'models'"
      >
        模型池
        <span class="tab-count">{{ aiStore.models.length }}</span>
      </button>
      <button
        class="tab"
        :class="{ active: tab === 'configs' }"
        @click="tab = 'configs'"
      >
        运行配置
        <span class="tab-count">{{ aiStore.configs.length }}</span>
      </button>
      <button
        class="tab"
        :class="{ active: tab === 'tools' }"
        @click="tab = 'tools'"
      >
        工具
        <span class="tab-count">{{ aiStore.tools.length }}</span>
      </button>
    </div>

    <div class="settings-body">
      <!-- ── Models ── -->
      <div v-show="tab === 'models'" class="panel">
        <div class="panel-toolbar">
          <span class="panel-title">模型池</span>
          <button class="btn btn-primary" @click="openCreateModel">
            <Icon name="plus" :size="14" :stroke-width="2.2" />
            新建模型
          </button>
        </div>

        <div v-if="aiStore.modelsLoading && !aiStore.models.length" class="empty">加载中…</div>
        <div v-else-if="!aiStore.models.length" class="empty">还没有模型，点击「新建模型」开始</div>
        <div v-else class="table-wrap">
          <table class="table">
            <thead>
              <tr>
                <th>名称</th>
                <th>格式</th>
                <th>模型标识</th>
                <th>Base URL</th>
                <th>API Key</th>
                <th>多模态</th>
                <th>Max Tokens</th>
                <th>状态</th>
                <th class="col-actions">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="m in aiStore.models" :key="m.model_id">
                <td class="cell-strong">{{ m.name }}</td>
                <td><code class="chip">{{ m.api_format }}</code></td>
                <td>{{ m.model }}</td>
                <td class="cell-mono ellipsis" :title="m.base_url">{{ m.base_url }}</td>
                <td class="cell-mono">{{ maskKey(m.api_key) }}</td>
                <td>
                  <span class="badge" :class="m.is_multimodal ? 'badge-on' : 'badge-off'">
                    {{ m.is_multimodal ? '是' : '否' }}
                  </span>
                </td>
                <td>{{ m.max_tokens }}</td>
                <td>
                  <span class="badge" :class="m.is_active ? 'badge-on' : 'badge-off'">
                    {{ m.is_active ? '启用' : '停用' }}
                  </span>
                </td>
                <td class="col-actions">
                  <button class="btn-icon" title="编辑" @click="openEditModel(m)">
                    <Icon name="edit" :size="15" />
                  </button>
                  <button class="btn-icon danger" title="删除" @click="onDeleteModel(m)">
                    <Icon name="trash" :size="15" />
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- ── Configs ── -->
      <div v-show="tab === 'configs'" class="panel">
        <div class="panel-toolbar">
          <span class="panel-title">运行配置</span>
          <button class="btn btn-primary" @click="openCreateConfig">
            <Icon name="plus" :size="14" :stroke-width="2.2" />
            新建配置
          </button>
        </div>

        <div v-if="aiStore.configsLoading && !aiStore.configs.length" class="empty">加载中…</div>
        <div v-else-if="!aiStore.configs.length" class="empty">还没有配置，点击「新建配置」开始</div>
        <div v-else class="table-wrap">
          <table class="table">
            <thead>
              <tr>
                <th>配置名称</th>
                <th>模型</th>
                <th>工具</th>
                <th>Temp</th>
                <th>Top P</th>
                <th>Max Tokens</th>
                <th>JSON</th>
                <th>状态</th>
                <th class="col-actions">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in aiStore.configs" :key="c.config_id">
                <td class="cell-strong">
                  {{ c.config_name }}
                  <span v-if="c.is_default" class="badge badge-default">默认</span>
                </td>
                <td>
                  <div class="model-cell">
                    <span>{{ c.model_name || '—' }}</span>
                    <span class="cell-sub" :title="c.model || ''">{{ c.model || '' }}</span>
                  </div>
                </td>
                <td class="ellipsis" :title="toolsLabel(c)">{{ toolsLabel(c) }}</td>
                <td>{{ paramLabel(c.temperature) }}</td>
                <td>{{ paramLabel(c.top_p) }}</td>
                <td>{{ paramLabel(c.max_tokens) }}</td>
                <td>
                  <span class="badge" :class="c.json_output ? 'badge-on' : 'badge-off'">
                    {{ c.json_output ? '是' : '否' }}
                  </span>
                </td>
                <td>
                  <span class="badge" :class="c.is_active ? 'badge-on' : 'badge-off'">
                    {{ c.is_active ? '启用' : '停用' }}
                  </span>
                </td>
                <td class="col-actions">
                  <button class="btn-icon" title="编辑" @click="openEditConfig(c)">
                    <Icon name="edit" :size="15" />
                  </button>
                  <button class="btn-icon danger" title="删除" @click="onDeleteConfig(c)">
                    <Icon name="trash" :size="15" />
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- ── Tools ── -->
      <div v-show="tab === 'tools'" class="panel">
        <div class="panel-toolbar">
          <span class="panel-title">工具注册表</span>
        </div>

        <div v-if="aiStore.toolsLoading && !aiStore.tools.length" class="empty">加载中…</div>
        <div v-else-if="!aiStore.tools.length" class="empty">暂无已注册工具</div>
        <div v-else class="tool-cards">
          <div v-for="t in aiStore.tools" :key="t.name" class="tool-card">
            <div class="tool-card-head">
              <code class="chip">{{ t.name }}</code>
            </div>
            <p class="tool-card-desc">{{ t.description }}</p>
            <details class="tool-params">
              <summary>参数定义</summary>
              <pre class="tool-params-body">{{ JSON.stringify(t.parameters, null, 2) }}</pre>
            </details>
          </div>
        </div>
      </div>
    </div>

    <AiModelFormModal v-model:visible="modelModalVisible" :model="editingModel" />
    <AiConfigFormModal v-model:visible="configModalVisible" :config="editingConfig" />
  </div>
</template>

<style scoped>
.settings-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--bg-main);
  min-width: 0;
  overflow: hidden;
}
.settings-header {
  padding: 14px 24px;
  border-bottom: 1px solid var(--border);
}
.title-area {
  display: flex;
  align-items: center;
  gap: 12px;
}
.title-icon {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--accent-light);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--accent);
  flex-shrink: 0;
}
.title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}
.subtitle {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 2px;
}
.tabs {
  display: flex;
  gap: 4px;
  padding: 0 20px;
  border-bottom: 1px solid var(--border);
}
.tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 14px;
  font-size: 13px;
  color: var(--text-secondary);
  border-bottom: 2px solid transparent;
  transition: color 0.15s, border-color 0.15s;
  margin-bottom: -1px;
}
.tab:hover {
  color: var(--text-primary);
}
.tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}
.tab-count {
  font-size: 11px;
  color: var(--text-tertiary);
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 0 6px;
  min-width: 18px;
  text-align: center;
}
.tab.active .tab-count {
  color: var(--accent);
}
.settings-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
}
.panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.panel-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}
.empty {
  font-size: 13px;
  color: var(--text-tertiary);
  padding: 24px 0;
  text-align: center;
}
.table-wrap {
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: auto;
  background: var(--bg-sidebar);
}
.table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.table th {
  text-align: left;
  font-weight: 600;
  font-size: 12px;
  color: var(--text-tertiary);
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-input);
  white-space: nowrap;
}
.table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  color: var(--text-secondary);
  vertical-align: middle;
}
.table tbody tr:last-child td {
  border-bottom: none;
}
.table tbody tr:hover {
  background: var(--bg-hover);
}
.cell-strong {
  color: var(--text-primary);
  font-weight: 500;
}
.cell-mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
}
.cell-sub {
  display: block;
  font-size: 11px;
  color: var(--text-tertiary);
}
.ellipsis {
  max-width: 220px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.col-actions {
  white-space: nowrap;
  display: flex;
  gap: 2px;
}
.col-actions .btn-icon {
  width: 28px;
  height: 28px;
}
.btn-icon.danger:hover {
  color: var(--danger);
}
.chip {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 6px;
  background: var(--bg-input);
  border: 1px solid var(--border);
  color: var(--text-secondary);
}
.badge {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 10px;
  font-weight: 500;
}
.badge-on {
  background: rgba(34, 197, 94, 0.15);
  color: #16a34a;
}
.badge-off {
  background: var(--bg-input);
  color: var(--text-tertiary);
}
.badge-default {
  margin-left: 6px;
  background: var(--accent-light);
  color: var(--accent);
}
.model-cell {
  display: flex;
  flex-direction: column;
}
.tool-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 320px), 1fr));
  gap: 14px;
}
.tool-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px;
  background: var(--bg-sidebar);
}
.tool-card-head {
  margin-bottom: 8px;
}
.tool-card-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin: 0 0 10px;
}
.tool-params summary {
  font-size: 12px;
  color: var(--text-tertiary);
  cursor: pointer;
}
.tool-params-body {
  margin: 8px 0 0;
  font-size: 11px;
  color: var(--text-secondary);
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px;
  overflow-x: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
</style>
