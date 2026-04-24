<script setup lang="ts">
import { ref, watch } from 'vue'
import { FileCheck, Upload, RotateCcw, X } from 'lucide-vue-next'

const props = defineProps<{
  visible: boolean
  fileName?: string
  canKeepResume?: boolean
}>()

const emit = defineEmits<{
  confirm: [choice: 'keep' | 'upload', file?: File]
  cancel: []
}>()

const choice = ref<'keep' | 'upload'>('keep')
const selectedFile = ref<File | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)

watch(() => props.visible, (visible) => {
  if (!visible) return
  choice.value = props.canKeepResume === false ? 'upload' : 'keep'
  selectedFile.value = null
})

function handleFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  selectedFile.value = input.files?.[0] || null
}

function triggerFileInput() {
  fileInputRef.value?.click()
}

function handleConfirm() {
  if (choice.value === 'keep' && props.canKeepResume === false) return
  if (choice.value === 'upload' && !selectedFile.value) return
  emit('confirm', choice.value, selectedFile.value || undefined)
}

function handleCancel() {
  choice.value = 'keep'
  selectedFile.value = null
  emit('cancel')
}
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="retry-overlay" @click.self="handleCancel">
      <div class="retry-modal">
        <!-- 头部 -->
        <div class="modal-header">
          <div class="flex items-center justify-between">
            <h2 class="modal-title">再面一次</h2>
            <button @click="handleCancel" class="p-1 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-white/70 transition">
              <X class="w-5 h-5" />
            </button>
          </div>
          <p class="modal-subtitle">选择简历后将直接进入面试房间</p>
        </div>

        <!-- 选项 -->
        <div class="modal-body">
          <!-- 使用上次简历 -->
          <button
            type="button"
            :disabled="props.canKeepResume === false"
            @click="props.canKeepResume !== false && (choice = 'keep')"
            class="option-card"
            :class="[
              choice === 'keep' ? 'option-active' : 'option-idle',
              props.canKeepResume === false ? 'option-disabled' : '',
            ]"
          >
            <div class="flex items-center gap-3">
              <div class="option-radio" :class="choice === 'keep' ? 'radio-active' : 'radio-idle'" />
              <div class="flex-1 text-left">
                <div class="option-title">使用上次简历</div>
                <div class="option-desc">
                  <template v-if="props.canKeepResume === false">
                    该记录没有可复用的简历解析结果，请改为上传新简历
                  </template>
                  <template v-else>
                    <FileCheck class="w-3.5 h-3.5 inline -mt-0.5 text-green-500" />
                    {{ fileName || '历史简历' }}
                  </template>
                </div>
              </div>
            </div>
          </button>

          <!-- 上传新简历 -->
          <button type="button" @click="choice = 'upload'"
            class="option-card" :class="choice === 'upload' ? 'option-active' : 'option-idle'">
            <div class="flex items-center gap-3">
              <div class="option-radio" :class="choice === 'upload' ? 'radio-active' : 'radio-idle'" />
              <div class="flex-1 text-left">
                <div class="option-title">上传新简历</div>
                <div class="option-desc">重新上传 PDF / DOCX / Markdown / TXT / 图片文件</div>
              </div>
            </div>
          </button>

          <!-- 文件选择（仅 upload 模式展开） -->
          <div v-if="choice === 'upload'" class="file-zone">
            <div v-if="!selectedFile" class="upload-area" @click="triggerFileInput">
              <Upload class="w-8 h-8 text-slate-400 dark:text-white/30 mb-2" />
              <p class="text-sm text-slate-500 dark:text-white/50">点击选择文件</p>
              <p class="text-xs text-slate-400 dark:text-white/30 mt-0.5">PDF / DOCX / MD / TXT / 图片</p>
              <input ref="fileInputRef" type="file" accept=".pdf,.docx,.md,.markdown,.txt,.png,.jpg,.jpeg,.bmp,.webp,.heic,.heif" class="hidden" @change="handleFileSelect" />
            </div>
            <div v-else class="file-selected">
              <FileCheck class="w-5 h-5 text-green-500 shrink-0" />
              <span class="text-sm text-slate-700 dark:text-white/80 truncate flex-1">{{ selectedFile.name }}</span>
              <button @click="selectedFile = null" class="text-slate-400 hover:text-red-500 transition">
                <X class="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        <!-- 底部 -->
        <div class="modal-footer">
          <button @click="handleCancel" class="btn-secondary">取消</button>
          <button @click="handleConfirm" class="btn-primary"
            :disabled="choice === 'upload' && !selectedFile">
            <RotateCcw class="w-4 h-4" /> 开始面试
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
@reference "tailwindcss";

.retry-overlay {
  @apply fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4;
  animation: fadeIn 0.2s ease-out;
}

.retry-modal {
  @apply bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-md w-full;
  animation: slideUp 0.3s ease-out;
}

.modal-header {
  @apply p-6 pb-4;
}

.modal-title {
  @apply text-lg font-bold text-slate-900 dark:text-white;
}

.modal-subtitle {
  @apply text-sm text-slate-500 dark:text-slate-400 mt-1;
}

.modal-body {
  @apply px-6 space-y-3;
}

.option-card {
  @apply w-full p-4 rounded-xl border transition-all;
}

.option-active {
  border-color: var(--color-primary);
  background: color-mix(in srgb, var(--color-primary) 5%, transparent);
}

.option-idle {
  @apply border-slate-200 dark:border-white/10 hover:border-slate-300 dark:hover:border-white/20;
}

.option-disabled {
  @apply cursor-not-allowed opacity-60;
}

.option-radio {
  @apply w-4 h-4 rounded-full border-2 shrink-0 transition-all;
}

.radio-active {
  border-color: var(--color-primary);
  background: var(--color-primary);
  box-shadow: inset 0 0 0 2px white;
}

.radio-idle {
  @apply border-slate-300 dark:border-white/30;
}

.option-title {
  @apply text-sm font-bold text-slate-800 dark:text-white/90;
}

.option-desc {
  @apply text-xs text-slate-500 dark:text-white/50 mt-0.5;
}

.file-zone {
  animation: fadeIn 0.2s ease-out;
}

.upload-area {
  @apply border-2 border-dashed border-slate-300 dark:border-slate-600 rounded-xl p-6 text-center cursor-pointer transition-colors;
  @apply hover:border-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-900/10;
}

.file-selected {
  @apply flex items-center gap-3 px-4 py-3 bg-slate-50 dark:bg-slate-900 rounded-xl;
}

.modal-footer {
  @apply p-6 pt-4 flex justify-end gap-3;
}

.btn-secondary {
  @apply px-4 py-2 rounded-xl text-sm font-medium text-slate-700 dark:text-slate-300 bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 transition;
}

.btn-primary {
  @apply px-4 py-2 rounded-xl text-sm font-medium text-white bg-indigo-500 hover:bg-indigo-600 transition inline-flex items-center gap-2 disabled:opacity-50;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
