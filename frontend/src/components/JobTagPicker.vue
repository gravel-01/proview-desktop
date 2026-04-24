<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { RefreshCw } from 'lucide-vue-next'
import api from '../services/api'

const props = defineProps<{ modelValue: string; defaultExpanded?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const allPositions = ref<string[]>([])
const expanded = ref(props.defaultExpanded ?? false)
const searchMode = ref(false)
const displayTags = ref<string[]>([])

const BATCH_SIZE = 8

const TAG_COLORS = [
  { bg: '#FFF0F0', text: '#E03131', border: '#FFC9C9' },
  { bg: '#FFF4E6', text: '#E8590C', border: '#FFD8A8' },
  { bg: '#FFF9DB', text: '#E67700', border: '#FFE066' },
  { bg: '#EBFBEE', text: '#2F9E44', border: '#B2F2BB' },
  { bg: '#E6FCF5', text: '#099268', border: '#96F2D7' },
  { bg: '#E7F5FF', text: '#1971C2', border: '#A5D8FF' },
  { bg: '#EDF2FF', text: '#4263EB', border: '#BAC8FF' },
  { bg: '#F8F0FC', text: '#AE3EC9', border: '#EEBEFA' },
]

const filteredPositions = computed(() => {
  if (!props.modelValue.trim()) return []
  const q = props.modelValue.trim().toLowerCase()
  return allPositions.value.filter(p => p.toLowerCase().includes(q)).slice(0, 12)
})

const visibleTags = computed(() => {
  if (searchMode.value && props.modelValue.trim()) return filteredPositions.value
  return displayTags.value
})

function shuffleTags() {
  const pool = [...allPositions.value]
  const result: string[] = []
  while (result.length < BATCH_SIZE && pool.length > 0) {
    const idx = Math.floor(Math.random() * pool.length)
    const item = pool.splice(idx, 1)[0]
    if (item) result.push(item)
  }
  displayTags.value = result
}

function onInput(e: Event) {
  const val = (e.target as HTMLInputElement).value
  emit('update:modelValue', val)
  searchMode.value = val.trim().length > 0 && expanded.value
}

function selectTag(tag: string) {
  emit('update:modelValue', tag)
  searchMode.value = false
}

function getColor(index: number) {
  return TAG_COLORS[index % TAG_COLORS.length]!
}

onMounted(async () => {
  try {
    const { data } = await api.get('/api/positions')
    allPositions.value = data.positions || []
    shuffleTags()
  } catch (e) {
    console.error('加载岗位数据失败:', e)
  }
})
</script>

<template>
  <div>
    <input
      :value="modelValue"
      @input="onInput"
      type="text"
      placeholder="在这里填写岗位"
      class="config-input w-full"
    />

    <!-- 展开/收起按钮 -->
    <button
      v-if="allPositions.length > 0"
      type="button"
      @click="expanded = !expanded"
      class="mt-2 text-xs text-primary hover:text-indigo-700 dark:hover:text-indigo-300 font-medium transition-colors"
    >
      {{ expanded ? '收起岗位推荐' : '🔍 查看更多岗位推荐' }}
    </button>

    <!-- 标签区域 -->
    <div v-if="expanded && allPositions.length > 0" class="mt-3">
      <div class="flex items-center justify-between mb-2">
        <span class="text-xs text-slate-400 dark:text-slate-500">
          {{ searchMode && modelValue.trim() ? `搜索到 ${visibleTags.length} 个岗位` : '岗位快速检索，点击标签选择' }}
        </span>
        <button
          v-if="!searchMode || !modelValue.trim()"
          type="button"
          @click="shuffleTags"
          class="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-primary dark:text-slate-400 dark:hover:text-indigo-400 transition-colors"
        >
          <RefreshCw class="w-3 h-3" /> 换一批
        </button>
      </div>

      <div class="flex flex-wrap gap-2">
        <button
          v-for="(tag, i) in visibleTags"
          :key="tag"
          type="button"
          @click="selectTag(tag)"
          class="job-tag"
          :style="{
            backgroundColor: getColor(i).bg,
            color: getColor(i).text,
            borderColor: getColor(i).border,
          }"
        >
          {{ tag }}
        </button>
        <span v-if="visibleTags.length === 0 && searchMode" class="text-xs text-slate-400 py-1">
          未找到匹配岗位，可直接输入自定义岗位
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
@reference "tailwindcss";

.job-tag {
  @apply px-3 py-1.5 rounded-full text-xs font-bold border transition-all cursor-pointer;
}
.job-tag:hover {
  filter: brightness(0.95);
  transform: translateY(-1px);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
}

:root.dark .job-tag,
.dark .job-tag {
  filter: brightness(0.7) saturate(1.2);
}
:root.dark .job-tag:hover,
.dark .job-tag:hover {
  filter: brightness(0.8) saturate(1.2);
}
</style>
