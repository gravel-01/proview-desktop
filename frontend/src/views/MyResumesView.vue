<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  ChevronLeft,
  ChevronRight,
  Download,
  Eye,
  FileText,
  FileUser,
  Loader,
  Search,
  Trash2,
  X,
} from 'lucide-vue-next'
import {
  deleteMyResume,
  fetchMyResumes,
  getResumeFileUrl,
  getResumePreviewUrl,
  type ResumeRecord,
} from '../services/interview'

const RESUME_LIMIT = 5

const resumes = ref<ResumeRecord[]>([])
const loading = ref(true)
const deletingId = ref<number | null>(null)
const previewResume = ref<ResumeRecord | null>(null)
const previewPage = ref(0)
const previewZoomed = ref(false)

async function loadResumes() {
  loading.value = true
  try {
    resumes.value = await fetchMyResumes()
  } finally {
    loading.value = false
  }
}

onMounted(loadResumes)
onBeforeUnmount(() => {
  previewResume.value = null
})

const previewImages = computed(() => {
  const resume = previewResume.value
  if (!resume) return []
  if (resume.preview_image_urls?.length) return resume.preview_image_urls
  return [getResumePreviewUrl(resume.id, 1)]
})

const activePreviewUrl = computed(() => previewImages.value[previewPage.value] || '')

function formatTime(value: string) {
  if (!value) return '未知时间'
  try {
    const date = new Date(value)
    return `${date.toLocaleDateString('zh-CN')} ${date.toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
    })}`
  } catch {
    return value
  }
}

function formatKind(record: ResumeRecord) {
  switch (record.file_kind) {
    case 'pdf':
      return 'PDF'
    case 'docx':
      return 'Word'
    case 'doc':
      return 'DOC'
    case 'image':
      return '图片'
    default:
      return '文件'
  }
}

function previewCover(record: ResumeRecord) {
  return record.preview_cover_url || getResumePreviewUrl(record.id, 1)
}

function previewPageLabel(record: ResumeRecord) {
  const count = record.preview_page_count || 0
  if (count <= 1) return `${formatKind(record)} 预览`
  return `${count} 页预览`
}

function openPreview(record: ResumeRecord) {
  previewResume.value = record
  previewPage.value = 0
  previewZoomed.value = false
}

function closePreview() {
  previewResume.value = null
  previewPage.value = 0
  previewZoomed.value = false
}

function toggleZoom() {
  previewZoomed.value = !previewZoomed.value
}

function previousPage() {
  if (!previewImages.value.length) return
  previewPage.value = previewPage.value === 0 ? previewImages.value.length - 1 : previewPage.value - 1
}

function nextPage() {
  if (!previewImages.value.length) return
  previewPage.value = previewPage.value === previewImages.value.length - 1 ? 0 : previewPage.value + 1
}

async function handleDelete(record: ResumeRecord) {
  const confirmed = window.confirm(`确定删除简历《${record.file_name}》吗？删除后会同时清理云端文件和预览图。`)
  if (!confirmed) return

  deletingId.value = record.id
  try {
    await deleteMyResume(record.id)
    if (previewResume.value?.id === record.id) {
      closePreview()
    }
    resumes.value = resumes.value.filter((item) => item.id !== record.id)
  } catch (error: any) {
    alert(error?.response?.data?.message || error?.message || '删除失败，请稍后重试。')
  } finally {
    deletingId.value = null
  }
}
</script>

<template>
  <div class="fade-in min-h-full max-w-6xl mx-auto">
    <div class="mb-6">
      <h2 class="flex items-center gap-2 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl dark:text-white">
        <FileUser class="h-7 w-7 text-primary" />
        我的简历
      </h2>
      <p class="mt-2 text-sm font-medium text-slate-500 dark:text-slate-400">
        系统只保留最近 {{ RESUME_LIMIT }} 份上传简历，并统一提供图片化预览。
      </p>
    </div>

    <div class="mb-5 rounded-2xl border border-amber-200 bg-amber-50/80 px-4 py-3 text-sm text-amber-800 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-200">
      最多保留最近 {{ RESUME_LIMIT }} 份简历。上传第 {{ RESUME_LIMIT + 1 }} 份时，最早的一份会被自动删除，并同步清理服务器文件与预览图。
    </div>

    <div v-if="loading" class="flex items-center justify-center py-20">
      <Loader class="h-6 w-6 animate-spin text-primary" />
      <span class="ml-2 text-slate-500 dark:text-slate-400">正在加载简历库...</span>
    </div>

    <div v-else-if="!resumes.length" class="py-20 text-center">
      <FileUser class="mx-auto mb-4 h-16 w-16 text-slate-300 dark:text-slate-600" />
      <p class="text-slate-500 dark:text-slate-400">暂无简历记录</p>
      <p class="mt-1 text-sm text-slate-400 dark:text-slate-500">在面试配置中上传简历后，这里会自动生成预览卡片。</p>
    </div>

    <div v-else class="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-3">
      <article
        v-for="record in resumes"
        :key="record.id"
        class="resume-card group"
      >
        <button
          type="button"
          class="resume-thumb"
          @click="openPreview(record)"
        >
          <img
            v-if="record.can_preview !== false"
            :src="previewCover(record)"
            :alt="record.file_name"
            class="h-full w-full object-cover transition duration-300 group-hover:scale-[1.02]"
          />
          <div
            v-else
            class="flex h-full w-full flex-col items-center justify-center gap-3 text-slate-400 dark:text-slate-500"
          >
            <FileText class="h-10 w-10" />
            <span class="text-xs">暂无可用预览</span>
          </div>
          <div class="thumb-overlay">
            <Eye class="h-6 w-6 text-white" />
            <span class="text-sm font-medium text-white">查看预览</span>
          </div>
        </button>

        <div class="space-y-3 p-4">
          <div>
            <p class="truncate text-sm font-semibold text-slate-800 dark:text-white/90">{{ record.file_name }}</p>
            <p class="mt-1 text-xs text-slate-400 dark:text-slate-500">{{ formatTime(record.upload_time) }}</p>
          </div>

          <div class="flex flex-wrap items-center gap-2 text-xs">
            <span class="meta-badge">{{ previewPageLabel(record) }}</span>
            <span class="meta-badge">{{ formatKind(record) }}</span>
          </div>

          <div class="flex items-center gap-2">
            <button
              type="button"
              class="action-btn action-primary"
              @click="openPreview(record)"
            >
              <Eye class="h-4 w-4" />
              预览
            </button>
            <a
              :href="getResumeFileUrl(record.id)"
              download
              class="action-btn"
            >
              <Download class="h-4 w-4" />
              下载
            </a>
            <button
              type="button"
              class="action-btn action-danger ml-auto"
              :disabled="deletingId === record.id"
              @click="handleDelete(record)"
            >
              <Loader v-if="deletingId === record.id" class="h-4 w-4 animate-spin" />
              <Trash2 v-else class="h-4 w-4" />
              删除
            </button>
          </div>
        </div>
      </article>
    </div>

    <Teleport to="body">
      <div
        v-if="previewResume"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
        @click.self="closePreview"
      >
        <div class="preview-shell">
          <div class="preview-header">
            <div class="min-w-0">
              <h3 class="truncate text-sm font-bold text-slate-800 dark:text-white">{{ previewResume.file_name }}</h3>
              <p class="mt-1 text-xs text-slate-400 dark:text-slate-500">
                {{ previewResume.preview_page_count || 1 }} 页图片预览，点击大图可放大查看。
              </p>
            </div>
            <div class="flex items-center gap-2">
              <a
                :href="getResumeFileUrl(previewResume.id)"
                download
                class="icon-btn"
              >
                <Download class="h-4 w-4" />
              </a>
              <button
                type="button"
                class="icon-btn"
                @click="closePreview"
              >
                <X class="h-4 w-4" />
              </button>
            </div>
          </div>

          <div class="preview-layout">
            <aside v-if="previewImages.length > 1" class="preview-sidebar">
              <button
                v-for="(url, index) in previewImages"
                :key="url"
                type="button"
                class="preview-thumb-item"
                :class="{ 'preview-thumb-active': previewPage === index }"
                @click="previewPage = index"
              >
                <img :src="url" :alt="`${previewResume.file_name} 第 ${index + 1} 页`" class="h-full w-full object-cover" />
                <span class="preview-thumb-index">{{ index + 1 }}</span>
              </button>
            </aside>

            <div class="preview-stage">
              <div class="preview-toolbar">
                <button type="button" class="icon-btn" @click="previousPage">
                  <ChevronLeft class="h-4 w-4" />
                </button>
                <span class="text-xs text-slate-500 dark:text-slate-400">
                  第 {{ previewPage + 1 }} / {{ previewImages.length || 1 }} 页
                </span>
                <button type="button" class="icon-btn" @click="nextPage">
                  <ChevronRight class="h-4 w-4" />
                </button>
              </div>

              <div class="preview-canvas" :class="{ 'preview-canvas-zoomed': previewZoomed }">
                <button
                  type="button"
                  class="zoom-hint"
                  @click="toggleZoom"
                >
                  <Search class="h-4 w-4" />
                  {{ previewZoomed ? '恢复适应' : '点击放大' }}
                </button>
                <img
                  v-if="activePreviewUrl"
                  :src="activePreviewUrl"
                  :alt="previewResume.file_name"
                  class="preview-image"
                  :class="{ 'preview-image-zoomed': previewZoomed }"
                  @click="toggleZoom"
                />
                <div v-else class="flex h-full items-center justify-center text-sm text-slate-400 dark:text-slate-500">
                  暂无可用预览图
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
@reference "tailwindcss";

.resume-card {
  @apply overflow-hidden rounded-3xl border transition-all;
  background: rgba(255, 255, 255, 0.82);
  border-color: rgba(148, 163, 184, 0.28);
  box-shadow: 0 10px 32px rgba(15, 23, 42, 0.08);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
}

.resume-card:hover {
  transform: translateY(-3px);
  border-color: rgba(79, 70, 229, 0.45);
  box-shadow: 0 16px 40px rgba(79, 70, 229, 0.14);
}

.dark .resume-card {
  background: rgba(24, 24, 34, 0.92);
  border-color: rgba(255, 255, 255, 0.08);
}

.dark .resume-card:hover {
  border-color: rgba(129, 140, 248, 0.45);
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.4);
}

.resume-thumb {
  @apply relative block w-full overflow-hidden text-left;
  height: 260px;
  background: linear-gradient(180deg, #f8fafc 0%, #e2e8f0 100%);
}

.dark .resume-thumb {
  background: linear-gradient(180deg, #111827 0%, #0f172a 100%);
}

.thumb-overlay {
  @apply absolute inset-0 flex flex-col items-center justify-center gap-2 opacity-0 transition-opacity;
  background: rgba(15, 23, 42, 0.42);
}

.group:hover .thumb-overlay {
  opacity: 1;
}

.meta-badge {
  @apply inline-flex items-center justify-center rounded-full px-2.5 py-1 text-[11px] font-bold leading-none;
  border: 1px solid rgba(148, 163, 184, 0.26);
  background: rgba(248, 250, 252, 0.92);
  color: #475569;
}

.dark .meta-badge {
  border-color: rgba(255, 255, 255, 0.14);
  background: rgba(255, 255, 255, 0.05);
  color: #cbd5e1;
}

.action-btn {
  @apply inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-medium transition-colors;
  border-color: rgba(148, 163, 184, 0.3);
  color: rgb(71, 85, 105);
  background: rgba(255, 255, 255, 0.82);
}

.action-btn:hover {
  border-color: rgba(99, 102, 241, 0.35);
  color: rgb(79, 70, 229);
  background: rgba(255, 255, 255, 0.95);
}

.dark .action-btn {
  border-color: rgba(255, 255, 255, 0.08);
  color: rgb(203, 213, 225);
  background: rgba(255, 255, 255, 0.03);
}

.dark .action-btn:hover {
  border-color: rgba(129, 140, 248, 0.45);
  color: rgb(224, 231, 255);
  background: rgba(99, 102, 241, 0.14);
}

.action-primary {
  border-color: transparent;
  color: white;
  background: linear-gradient(90deg, #3b82f6, #8b5cf6, #ec4899);
  box-shadow: 0 10px 24px rgba(99, 102, 241, 0.22);
}

.action-danger {
  color: rgb(220, 38, 38);
}

.action-danger:hover {
  border-color: rgba(220, 38, 38, 0.35);
  color: rgb(185, 28, 28);
}

.dark .action-danger {
  color: rgb(251, 113, 133);
}

.dark .action-danger:hover {
  border-color: rgba(251, 113, 133, 0.45);
  color: rgb(253, 164, 175);
  background: rgba(190, 24, 93, 0.16);
}

.preview-shell {
  @apply flex max-h-[88vh] w-full max-w-6xl flex-col overflow-hidden rounded-[28px] border shadow-2xl;
  background: rgba(255, 255, 255, 0.98);
  border-color: rgba(226, 232, 240, 0.9);
}

.dark .preview-shell {
  background: rgba(10, 14, 24, 0.98);
  border-color: rgba(255, 255, 255, 0.08);
}

.preview-header {
  @apply flex items-center justify-between gap-4 border-b px-5 py-4;
  border-color: rgba(226, 232, 240, 0.9);
}

.dark .preview-header {
  border-color: rgba(255, 255, 255, 0.08);
}

.preview-layout {
  @apply flex min-h-0 flex-1;
}

.preview-sidebar {
  @apply hidden w-32 shrink-0 gap-3 overflow-y-auto border-r p-4 md:flex md:flex-col;
  border-color: rgba(226, 232, 240, 0.9);
  background: rgba(248, 250, 252, 0.85);
}

.dark .preview-sidebar {
  border-color: rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.02);
}

.preview-thumb-item {
  @apply relative overflow-hidden rounded-2xl border text-left transition-all;
  height: 120px;
  border-color: rgba(203, 213, 225, 0.8);
}

.dark .preview-thumb-item {
  border-color: rgba(255, 255, 255, 0.1);
}

.preview-thumb-active {
  border-color: rgba(79, 70, 229, 0.55);
  box-shadow: 0 0 0 2px rgba(79, 70, 229, 0.18);
}

.preview-thumb-index {
  @apply absolute bottom-2 right-2 rounded-full px-2 py-0.5 text-[11px] font-semibold text-white;
  background: rgba(15, 23, 42, 0.7);
}

.preview-stage {
  @apply flex min-h-0 flex-1 flex-col;
}

.preview-toolbar {
  @apply flex items-center justify-center gap-3 border-b px-4 py-3;
  border-color: rgba(226, 232, 240, 0.9);
}

.dark .preview-toolbar {
  border-color: rgba(255, 255, 255, 0.08);
}

.preview-canvas {
  @apply relative flex-1 overflow-auto p-4 md:p-6;
  background:
    radial-gradient(circle at top left, rgba(99, 102, 241, 0.08), transparent 28%),
    linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
}

.dark .preview-canvas {
  background:
    radial-gradient(circle at top left, rgba(99, 102, 241, 0.12), transparent 28%),
    linear-gradient(180deg, #0f172a 0%, #020617 100%);
}

.preview-canvas-zoomed {
  cursor: zoom-out;
}

.zoom-hint {
  @apply absolute right-4 top-4 z-10 inline-flex items-center gap-1 rounded-full border px-3 py-1.5 text-xs font-medium;
  border-color: rgba(226, 232, 240, 0.95);
  background: rgba(255, 255, 255, 0.88);
  color: rgb(51, 65, 85);
}

.dark .zoom-hint {
  border-color: rgba(255, 255, 255, 0.1);
  background: rgba(15, 23, 42, 0.88);
  color: rgb(203, 213, 225);
}

.preview-image {
  @apply mx-auto block max-w-full rounded-2xl shadow-xl transition-transform;
  max-height: calc(88vh - 220px);
}

.preview-image-zoomed {
  max-width: none;
  max-height: none;
  width: auto;
  transform: scale(1.45);
  transform-origin: top center;
}

.icon-btn {
  @apply inline-flex items-center justify-center rounded-xl border p-2 transition-colors;
  border-color: rgba(226, 232, 240, 0.95);
  color: rgb(71, 85, 105);
}

.icon-btn:hover {
  border-color: rgba(79, 70, 229, 0.4);
  color: rgb(79, 70, 229);
}

.dark .icon-btn {
  border-color: rgba(255, 255, 255, 0.08);
  color: rgb(203, 213, 225);
}

.dark .icon-btn:hover {
  border-color: rgba(129, 140, 248, 0.45);
  color: rgb(224, 231, 255);
  background: rgba(99, 102, 241, 0.12);
}
</style>
