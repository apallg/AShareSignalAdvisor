<template>
  <div class="editor-layout">
    <div class="editor-sidebar">
      <div class="card-title" style="margin-bottom:8px">策略文件</div>
      <template v-for="group in fileGroups" :key="group.dir">
        <div class="file-group-label">{{ group.label }}</div>
        <div
          v-for="f in group.files" :key="f.path"
          class="file-item"
          :class="{ active: currentPath === f.path }"
          @click="loadFile(f.path)"
        >
          {{ f.name }}.py
          <span class="file-badge" v-if="!f.editable">只读</span>
        </div>
      </template>
      <div class="editor-sidebar-actions">
        <button class="btn" style="width:100%;margin-bottom:6px;background:#555" @click="openFolder">打开策略文件夹</button>
        <button class="btn" style="width:100%" @click="newStrategy">+ 新建</button>
      </div>
    </div>

    <div class="editor-main">
      <div v-if="!currentPath" class="empty">请从左侧选择策略文件，或点击"新建"创建策略</div>
      <template v-else>
        <div class="editor-toolbar">
          <span class="editor-path">{{ currentPath }}</span>
          <span v-if="!editable" class="tag tag-mid">只读</span>
          <div style="margin-left:auto;display:flex;gap:8px">
            <button v-if="editable" class="btn" @click="saveFile">保存</button>
            <button v-if="editable" class="btn" style="background:#c0392b" @click="deleteFile">删除</button>
          </div>
        </div>
        <textarea
          class="code-editor"
          v-model="code"
          :readonly="!editable"
          spellcheck="false"
        ></textarea>
      </template>
    </div>

    <div class="editor-ai">
      <div class="card-title">AI 策略助手</div>
      <p style="font-size:12px;color:#888;margin:4px 0 8px">描述你的策略想法，3 个 Agent 协作生成</p>
      <textarea
        class="ai-input"
        v-model="idea"
        placeholder="例如：我想做一个基于成交量的突破策略，当股价突破20日高点且成交量放大到5日均量的2倍时买入，跌破10日低点卖出..."
        rows="4"
      ></textarea>
      <button class="btn" style="width:100%" @click="generate" :disabled="generating">
        {{ generating ? '生成中...' : '⚡ 生成策略' }}
      </button>

      <div v-if="aiError" class="error" style="margin-top:8px">{{ aiError }}</div>

      <div v-if="result" class="ai-tabs">
        <div class="ai-tab-bar">
          <button :class="{ active: aiTab === 'code' }" @click="aiTab = 'code'">代码</button>
          <button :class="{ active: aiTab === 'codereview' }" @click="aiTab = 'codereview'">代码审查</button>
          <button :class="{ active: aiTab === 'logic' }" @click="aiTab = 'logic'">逻辑审查</button>
        </div>

        <div v-if="aiTab === 'code'" class="ai-panel">
          <div class="ai-panel-header">
            <span>工程师 · 生成代码</span>
            <button v-if="editable" class="btn" style="padding:3px 10px;font-size:12px" @click="applyGenerated">应用</button>
          </div>
          <pre class="ai-code-preview">{{ result.code }}</pre>
        </div>

        <div v-if="aiTab === 'codereview'" class="ai-panel">
          <div class="ai-panel-header">
            <span>代码审查 · 质量检查</span>
          </div>
          <pre class="ai-review-text">{{ result.code_review }}</pre>
        </div>

        <div v-if="aiTab === 'logic'" class="ai-panel">
          <div class="ai-panel-header">
            <span>基金经理 · 逻辑审查</span>
          </div>
          <pre class="ai-review-text">{{ result.logic_review }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import api from '../api'

const files = ref([])
const currentPath = ref('')
const code = ref('')
const editable = ref(false)
const idea = ref('')
const generating = ref(false)
const result = ref(null)
const aiTab = ref('code')
const aiError = ref('')

const fileGroups = computed(() => {
  const groups = [
    { dir: 'classic', label: '内置经典', files: [] },
    { dir: 'hybrid', label: 'AI/情绪混合', files: [] },
    { dir: 'custom', label: '自定义', files: [] },
    { dir: 'community', label: '社区', files: [] },
  ]
  for (const f of files.value) {
    const g = groups.find(g => g.dir === f.dir)
    if (g) g.files.push(f)
  }
  return groups.filter(g => g.files.length > 0)
})

async function fetchFiles() {
  const { data } = await api.get('/strategies/files')
  files.value = data
}

onMounted(fetchFiles)

async function loadFile(path) {
  const { data } = await api.get('/strategies/file', { params: { path } })
  currentPath.value = path
  code.value = data.code
  editable.value = data.editable
  result.value = null
  aiTab.value = 'code'
  aiError.value = ''
}

async function saveFile() {
  await api.post('/strategies/file', { path: currentPath.value, code: code.value })
  alert('保存成功')
}

async function deleteFile() {
  if (!confirm(`确定删除 ${currentPath.value}？`)) return
  await api.delete('/strategies/file', { params: { path: currentPath.value } })
  currentPath.value = ''
  code.value = ''
  fetchFiles()
}

async function newStrategy() {
  const name = prompt('策略文件名（不含 .py）：')
  if (!name) return
  const path = `custom/${name}.py`
  const { data } = await api.get('/strategies/template', { params: { name } })
  await api.post('/strategies/file', { path, code: data.code })
  await fetchFiles()
  currentPath.value = path
  code.value = data.code
  editable.value = true
}

async function generate() {
  if (!idea.value.trim()) return
  generating.value = true
  result.value = null
  aiError.value = ''
  aiTab.value = 'code'
  try {
    const { data } = await api.post('/strategies/generate', { idea: idea.value })
    result.value = data
  } catch (e) {
    aiError.value = e.message || '生成失败'
  }
  generating.value = false
}

function applyGenerated() {
  if (result.value) code.value = result.value.code
}

async function openFolder() {
  try {
    const { data } = await api.get('/strategies/open-dir')
    const path = data.path
    if (!path) throw new Error('未获取到目录路径')
    // 方法1: 尝试直接打开（需浏览器允许 file:// 协议）
    const fileUrl = 'file:///' + path.replace(/\\/g, '/')
    const w = window.open(fileUrl, '_blank')
    if (!w || w.closed || typeof w.closed === 'undefined') {
      // 方法2: 自动下载 .bat 文件，双击即可打开文件夹
      const a = document.createElement('a')
      a.href = '/api/strategies/open-dir-bat'
      a.download = '打开策略文件夹.bat'
      a.click()
      await navigator.clipboard.writeText(path)
      alert('已下载"打开策略文件夹.bat"，双击即可打开\n\n路径已复制: ' + path)
    }
  } catch (e) {
    alert('打开目录失败: ' + (e.message || e))
  }
}
</script>

<style scoped>
.editor-layout { display: flex; height: calc(100vh - 120px); gap: 16px; }
.editor-sidebar { width: 200px; background: #fff; border-radius: 8px; padding: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); display: flex; flex-direction: column; overflow-y: auto; }
.editor-main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.editor-ai { width: 320px; background: #fff; border-radius: 8px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); display: flex; flex-direction: column; overflow-y: auto; }
.file-group-label { font-size: 11px; color: #999; padding: 8px 4px 4px; font-weight: 600; text-transform: uppercase; }
.file-item { padding: 6px 8px; font-size: 13px; color: #333; cursor: pointer; border-radius: 4px; display: flex; align-items: center; gap: 6px; }
.file-item:hover { background: #f5f6fa; }
.file-item.active { background: #16213e; color: #fff; }
.file-badge { font-size: 10px; color: #999; margin-left: auto; }
.editor-sidebar-actions { margin-top: auto; padding-top: 12px; border-top: 1px solid #eee; }
.editor-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.editor-path { font-size: 13px; color: #666; font-family: monospace; }
.code-editor { flex: 1; width: 100%; min-height: 0; padding: 16px; border: 1px solid #ddd; border-radius: 6px; font-family: 'Consolas', 'Fira Code', monospace; font-size: 13px; line-height: 1.5; resize: none; outline: none; background: #1a1a2e; color: #e0e0e0; tab-size: 4; }
.code-editor[readonly] { background: #f5f5f5; color: #333; }
.ai-input { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 13px; resize: vertical; outline: none; margin-bottom: 8px; }
.ai-tabs { margin-top: 12px; flex: 1; display: flex; flex-direction: column; min-height: 0; }
.ai-tab-bar { display: flex; gap: 2px; margin-bottom: 8px; }
.ai-tab-bar button { flex: 1; padding: 6px 4px; border: 1px solid #ddd; background: #f5f5f5; font-size: 11px; cursor: pointer; border-radius: 4px 4px 0 0; transition: all 0.2s; }
.ai-tab-bar button.active { background: #e94560; color: #fff; border-color: #e94560; }
.ai-panel { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.ai-panel-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; font-size: 12px; color: #888; }
.ai-code-preview { background: #1a1a2e; color: #e0e0e0; padding: 12px; border-radius: 6px; font-size: 12px; line-height: 1.4; flex: 1; overflow-y: auto; white-space: pre-wrap; word-break: break-all; max-height: 260px; }
.ai-review-text { background: #f8f9fa; color: #333; padding: 12px; border-radius: 6px; font-size: 12px; line-height: 1.6; flex: 1; overflow-y: auto; white-space: pre-wrap; word-break: break-all; }
</style>
