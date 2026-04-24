<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ChevronDown, Check } from 'lucide-vue-next'

interface Option {
  value: number | string
  label: string
}

interface Props {
  modelValue: number | string
  options: Option[]
  placeholder?: string
}

const props = withDefaults(defineProps<Props>(), {
  placeholder: '请选择'
})

const emit = defineEmits<{
  'update:modelValue': [value: number | string]
}>()

const isOpen = ref(false)
const selectRef = ref<HTMLDivElement | null>(null)

const selectedOption = computed(() => {
  return props.options.find(opt => opt.value === props.modelValue)
})

function selectOption(value: number | string) {
  emit('update:modelValue', value)
  isOpen.value = false
}

function toggleDropdown() {
  isOpen.value = !isOpen.value
}

// 点击外部关闭下拉菜单
function handleClickOutside(event: MouseEvent) {
  if (selectRef.value && !selectRef.value.contains(event.target as Node)) {
    isOpen.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>

<template>
  <div ref="selectRef" class="custom-select-wrapper" :class="{ 'custom-select-wrapper--open': isOpen }">
    <button
      type="button"
      @click="toggleDropdown"
      class="custom-select-trigger"
      :class="{ 'custom-select-open': isOpen }"
    >
      <span class="custom-select-value">
        {{ selectedOption?.label || placeholder }}
      </span>
      <ChevronDown class="custom-select-icon" :class="{ 'rotate-180': isOpen }" />
    </button>

    <Transition name="dropdown">
      <div v-if="isOpen" class="custom-select-dropdown">
        <button
          v-for="option in options"
          :key="option.value"
          type="button"
          @click="selectOption(option.value)"
          class="custom-select-option"
          :class="{ 'custom-select-option-selected': option.value === modelValue }"
        >
          <span>{{ option.label }}</span>
          <Check v-if="option.value === modelValue" class="w-4 h-4" />
        </button>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
@reference "tailwindcss";

.custom-select-wrapper {
  @apply relative;
  z-index: 1;
}

.custom-select-wrapper--open {
  z-index: 40;
}

.custom-select-trigger {
  @apply w-full px-4 py-3 rounded-xl border outline-none transition-all flex items-center justify-between;
  background: transparent;
  border-color: rgb(203, 213, 225);
  color: rgb(15, 23, 42);
}

.dark .custom-select-trigger {
  background: #0F0F15;
  border-color: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.95);
}

.custom-select-trigger:hover {
  border-color: rgb(148, 163, 184);
}

.dark .custom-select-trigger:hover {
  border-color: rgba(255, 255, 255, 0.2);
}

.custom-select-open {
  border-color: var(--color-primary) !important;
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--color-primary) 30%, transparent);
}

.custom-select-value {
  @apply text-sm flex-1 text-left;
}

.custom-select-icon {
  @apply w-4 h-4 transition-transform;
  color: rgb(148, 163, 184);
}

.dark .custom-select-icon {
  color: rgba(255, 255, 255, 0.4);
}

.custom-select-dropdown {
  @apply absolute left-0 right-0 mt-2 rounded-xl border overflow-hidden z-50;
  max-height: 240px;
  overflow-y: auto;
  background: white;
  border-color: rgb(226, 232, 240);
  box-shadow:
    0 24px 48px -18px rgba(15, 23, 42, 0.3),
    0 10px 18px -8px rgba(15, 23, 42, 0.14);
}

.dark .custom-select-dropdown {
  /* 暗黑模式：使用悬浮层级颜色 */
  background: #1E1E2E;
  border-color: rgba(255, 255, 255, 0.1);
  box-shadow:
    0 24px 48px -18px rgba(0, 0, 0, 0.55),
    0 12px 20px -10px rgba(0, 0, 0, 0.4);
}

.custom-select-option {
  @apply w-full px-4 py-2.5 text-left text-sm transition-colors flex items-center justify-between;
  color: rgb(15, 23, 42);
}

.dark .custom-select-option {
  color: rgba(255, 255, 255, 0.95);
}

.custom-select-option:hover {
  background: rgb(248, 250, 252);
}

.dark .custom-select-option:hover {
  background: rgba(255, 255, 255, 0.1);
}

.custom-select-option-selected {
  color: var(--color-primary);
  font-weight: 500;
}

.dark .custom-select-option-selected {
  color: var(--color-primary);
}

/* 下拉动画 */
.dropdown-enter-active,
.dropdown-leave-active {
  transition: all 0.2s ease;
}

.dropdown-enter-from {
  opacity: 0;
  transform: translateY(-8px);
}

.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* 自定义滚动条 */
.custom-select-dropdown::-webkit-scrollbar {
  width: 6px;
}

.custom-select-dropdown::-webkit-scrollbar-track {
  background: transparent;
}

.custom-select-dropdown::-webkit-scrollbar-thumb {
  background: rgb(203, 213, 225);
  border-radius: 10px;
}

.dark .custom-select-dropdown::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.2);
}
</style>
