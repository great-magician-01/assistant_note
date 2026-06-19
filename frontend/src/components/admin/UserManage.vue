<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import dayjs from 'dayjs'
import Icon from '@/components/Icon.vue'
import Modal from '@/components/Modal.vue'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import { extractErrorMessage } from '@/api/client'
import * as userApi from '@/api/user'
import { USER_AUDIT_STATUS, type UserItem } from '@/types'

const props = defineProps<{
  /** Whether this view is the active one — drives lazy loading. */
  visible: boolean
}>()

const authStore = useAuthStore()
const toast = useToast()

type Filter = 'all' | 'pending' | 'approved' | 'rejected'
const FILTERS: { key: Filter; label: string; status: number | null }[] = [
  { key: 'all', label: '全部', status: null },
  { key: 'pending', label: '待审核', status: USER_AUDIT_STATUS.PENDING },
  { key: 'approved', label: '已通过', status: USER_AUDIT_STATUS.APPROVED },
  { key: 'rejected', label: '已拒绝', status: USER_AUDIT_STATUS.REJECTED },
]
const filter = ref<Filter>('pending')
const keyword = ref('')
const page = ref(1)
const pageSize = 20
const total = ref(0)
const items = ref<UserItem[]>([])
const loading = ref(false)

const currentUserId = computed(() => authStore.user?.user_id ?? '')

// Reset-password modal state.
const resetVisible = ref(false)
const resetTarget = ref<UserItem | null>(null)
const newPassword = ref('')
const resetting = ref(false)

let loaded = false
async function ensureLoaded() {
  if (loaded || !authStore.isAdmin) return
  loaded = true
  await fetchList()
}
watch(
  () => props.visible,
  (v) => {
    if (v) void ensureLoaded()
  },
  { immediate: true },
)

async function fetchList() {
  loading.value = true
  try {
    const f = FILTERS.find((x) => x.key === filter.value)!
    const res = await userApi.listUsers({
      status: f.status,
      keyword: keyword.value.trim() || null,
      page: page.value,
      page_size: pageSize,
    })
    items.value = res.items
    total.value = res.total
  } catch (err) {
    toast.error(extractErrorMessage(err, '加载用户列表失败'))
  } finally {
    loading.value = false
  }
}

// Debounced keyword search.
let keywordTimer: number | undefined
watch(keyword, () => {
  if (keywordTimer) window.clearTimeout(keywordTimer)
  keywordTimer = window.setTimeout(() => {
    page.value = 1
    void fetchList()
  }, 300)
})
watch(filter, () => {
  page.value = 1
  void fetchList()
})

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
function prevPage() {
  if (page.value > 1) {
    page.value--
    void fetchList()
  }
}
function nextPage() {
  if (page.value < totalPages.value) {
    page.value++
    void fetchList()
  }
}

function auditLabel(s: number): string {
  if (s === USER_AUDIT_STATUS.PENDING) return '待审核'
  if (s === USER_AUDIT_STATUS.APPROVED) return '已通过'
  return '已拒绝'
}
function auditClass(s: number): string {
  if (s === USER_AUDIT_STATUS.PENDING) return 'badge-warn'
  if (s === USER_AUDIT_STATUS.APPROVED) return 'badge-on'
  return 'badge-danger'
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = dayjs(iso)
  return d.isValid() ? d.format('YYYY-MM-DD HH:mm') : ''
}

const isSelf = (u: UserItem) => u.user_id === currentUserId.value

async function onApprove(u: UserItem) {
  try {
    await userApi.approveUser(u.user_id)
    toast.success(`已通过「${u.user_account}」`)
    await fetchList()
  } catch (err) {
    toast.error(extractErrorMessage(err, '操作失败'))
  }
}
async function onReject(u: UserItem) {
  if (!window.confirm(`确定拒绝「${u.user_account}」的注册申请？`)) return
  try {
    await userApi.rejectUser(u.user_id)
    toast.success(`已拒绝「${u.user_account}」`)
    await fetchList()
  } catch (err) {
    toast.error(extractErrorMessage(err, '操作失败'))
  }
}
async function onToggleActive(u: UserItem) {
  const next = u.is_active === 1 ? 0 : 1
  try {
    await userApi.updateUser(u.user_id, { is_active: next })
    toast.success(next === 1 ? `已启用「${u.user_account}」` : `已禁用「${u.user_account}」`)
    await fetchList()
  } catch (err) {
    toast.error(extractErrorMessage(err, '操作失败'))
  }
}
function openReset(u: UserItem) {
  resetTarget.value = u
  newPassword.value = ''
  resetVisible.value = true
}
async function confirmReset() {
  if (!resetTarget.value) return
  if (newPassword.value.length < 6) {
    toast.error('密码至少 6 位')
    return
  }
  resetting.value = true
  try {
    await userApi.resetUserPassword(resetTarget.value.user_id, newPassword.value)
    toast.success(`已重置「${resetTarget.value.user_account}」的密码`)
    resetVisible.value = false
  } catch (err) {
    toast.error(extractErrorMessage(err, '重置失败'))
  } finally {
    resetting.value = false
  }
}
</script>

<template>
  <div class="user-view">
    <div class="view-header">
      <div class="title-area">
        <div class="title-icon">
          <Icon name="user" :size="20" />
        </div>
        <div>
          <div class="title">用户审核</div>
          <div class="subtitle">审核注册申请、启停账号、重置密码（管理员）</div>
        </div>
      </div>
    </div>

    <div class="tabs">
      <button
        v-for="f in FILTERS"
        :key="f.key"
        class="tab"
        :class="{ active: filter === f.key }"
        @click="filter = f.key"
      >
        {{ f.label }}
        <span v-if="f.key === filter" class="tab-count">{{ total }}</span>
      </button>

      <div class="search-box">
        <Icon name="search" :size="14" class="search-icon" />
        <input
          v-model="keyword"
          type="text"
          placeholder="账号 / 用户名"
          class="search-input"
        />
      </div>
    </div>

    <div class="view-body">
      <div v-if="loading && !items.length" class="empty">加载中…</div>
      <div v-else-if="!items.length" class="empty">
        {{ filter === 'pending' ? '暂无待审核用户' : '暂无用户' }}
      </div>
      <div v-else class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>账号</th>
              <th>用户名</th>
              <th>角色</th>
              <th>审核状态</th>
              <th>启用</th>
              <th>注册时间</th>
              <th class="col-actions">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in items" :key="u.user_id">
              <td class="cell-strong">
                {{ u.user_account }}
                <span v-if="isSelf(u)" class="badge badge-self">我</span>
              </td>
              <td>{{ u.user_name }}</td>
              <td>
                <span class="chip">{{ u.role_name || u.role_code || '—' }}</span>
              </td>
              <td>
                <span class="badge" :class="auditClass(u.audit_status)">
                  {{ auditLabel(u.audit_status) }}
                </span>
              </td>
              <td>
                <span class="badge" :class="u.is_active === 1 ? 'badge-on' : 'badge-off'">
                  {{ u.is_active === 1 ? '启用' : '禁用' }}
                </span>
              </td>
              <td class="cell-mono">{{ formatDate(u.created_at) }}</td>
              <td class="col-actions">
                <template v-if="u.audit_status !== USER_AUDIT_STATUS.APPROVED">
                  <button class="btn btn-primary btn-sm" @click="onApprove(u)">通过</button>
                  <button
                    v-if="u.audit_status === USER_AUDIT_STATUS.PENDING"
                    class="btn btn-ghost btn-sm"
                    :disabled="isSelf(u)"
                    @click="onReject(u)"
                  >
                    拒绝
                  </button>
                </template>
                <template v-else>
                  <button
                    class="btn btn-ghost btn-sm"
                    :disabled="isSelf(u)"
                    :title="isSelf(u) ? '不能禁用自己的账号' : ''"
                    @click="onToggleActive(u)"
                  >
                    {{ u.is_active === 1 ? '禁用' : '启用' }}
                  </button>
                  <button class="btn btn-ghost btn-sm" @click="openReset(u)">重置密码</button>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="total > pageSize" class="pagination">
        <button class="btn btn-ghost btn-sm" :disabled="page <= 1" @click="prevPage">上一页</button>
        <span class="page-info">{{ page }} / {{ totalPages }}（共 {{ total }}）</span>
        <button class="btn btn-ghost btn-sm" :disabled="page >= totalPages" @click="nextPage">下一页</button>
      </div>
    </div>

    <Modal v-if="resetVisible" title="重置密码" width="420px" @close="resetVisible = false">
      <p class="reset-tip" v-if="resetTarget">
        为账号 <code class="chip">{{ resetTarget.user_account }}</code> 设置新密码
      </p>
      <label class="field">
        <span class="label">新密码 <span class="req">*</span></span>
        <input
          v-model="newPassword"
          type="password"
          class="input"
          placeholder="至少 6 位"
          autocomplete="new-password"
        />
      </label>
      <template #footer>
        <button class="btn btn-ghost" :disabled="resetting" @click="resetVisible = false">取消</button>
        <button class="btn btn-primary" :disabled="resetting" @click="confirmReset">
          {{ resetting ? '提交中…' : '确认重置' }}
        </button>
      </template>
    </Modal>
  </div>
</template>

<style scoped>
.user-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--bg-main);
  min-width: 0;
  overflow: hidden;
}
.view-header {
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
  align-items: center;
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
.search-box {
  position: relative;
  margin-left: auto;
  margin-bottom: 6px;
}
.search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-tertiary);
  pointer-events: none;
}
.search-input {
  width: 200px;
  height: 30px;
  padding: 0 10px 0 30px;
  font-size: 12px;
}
.view-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
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
  white-space: nowrap;
}
.col-actions {
  white-space: nowrap;
  display: flex;
  gap: 6px;
}
.btn-sm {
  padding: 4px 10px;
  font-size: 12px;
  border-radius: 6px;
}
.btn-sm:disabled {
  opacity: 0.5;
  cursor: not-allowed;
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
.badge-warn {
  background: rgba(245, 158, 11, 0.15);
  color: #d97706;
}
.badge-danger {
  background: rgba(239, 68, 68, 0.15);
  color: #dc2626;
}
.badge-self {
  margin-left: 6px;
  background: var(--accent-light);
  color: var(--accent);
}
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 16px;
}
.page-info {
  font-size: 12px;
  color: var(--text-tertiary);
}
/* Reset-password modal form fields */
.reset-tip {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0 0 14px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.label {
  font-size: 12px;
  color: var(--text-tertiary);
  font-weight: 500;
}
.req {
  color: var(--danger);
}
.input {
  height: 36px;
  padding: 0 12px;
  font-size: 14px;
}
</style>
