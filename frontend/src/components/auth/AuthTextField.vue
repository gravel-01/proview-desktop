<script setup lang="ts">
import { ref, computed, type Component } from 'vue'
import { Eye, EyeOff } from 'lucide-vue-next'

const props = withDefaults(
  defineProps<{
    modelValue: string
    label: string
    placeholder?: string
    type?: 'text' | 'password'
    autocomplete?: string
    error?: string
    required?: boolean
    icon: Component
    inputClass?: string
  }>(),
  {
    placeholder: '',
    type: 'text',
    autocomplete: 'off',
    error: '',
    required: false,
    inputClass: '',
  },
)

const emit = defineEmits<{
  'update:modelValue': [v: string]
  enter: []
}>()

const focused = ref(false)
const showPassword = ref(false)

const inputType = computed(() => {
  if (props.type === 'password' && showPassword.value) return 'text'
  return props.type
})

function onInput(e: Event) {
  emit('update:modelValue', (e.target as HTMLInputElement).value)
}
</script>

<template>
  <div class="auth-field" :class="{ 'auth-field--error': !!error }">
    <label class="mb-2 block text-xs font-medium text-gray-500 dark:text-slate-400">
      {{ label }}
      <span v-if="required" class="text-[#fb7185]">*</span>
    </label>
    <div
      class="rounded-lg transition-all duration-300 ease-out"
      :class="
        error
          ? 'bg-[#fb7185]/50 p-[1.5px] dark:bg-rose-400/35'
          : focused
            ? 'bg-gradient-to-br from-sky-300 via-indigo-300 to-violet-300 p-[2px] shadow-lg shadow-indigo-200/30 dark:shadow-indigo-900/25'
            : 'bg-gray-200/90 p-[1.5px] dark:bg-white/12'
      "
    >
      <div
        class="auth-field-control relative flex items-stretch rounded-[7px] shadow-sm transition-colors duration-300"
        :class="[
          focused && !error
            ? 'bg-white/70 dark:bg-slate-900/75'
            : 'bg-white/50 backdrop-blur-sm dark:bg-slate-900/45',
          error ? '!bg-[rgba(251,113,133,0.06)] dark:!bg-rose-950/30' : '',
        ]"
      >
        <span
          v-if="focused && !error"
          class="pointer-events-none absolute bottom-2.5 left-[2.35rem] top-2.5 w-0.5 rounded-full bg-gradient-to-b from-sky-400 to-indigo-400 opacity-90"
          aria-hidden="true"
        />
        <div
          class="relative z-[1] flex shrink-0 items-center pl-3 text-gray-400 transition-colors duration-300 dark:text-slate-500"
          :class="focused && !error ? '!text-sky-600 dark:!text-sky-400' : ''"
        >
          <component
            :is="icon"
            :size="18"
            class="auth-field-icon"
            :class="{ 'auth-field-icon--delay': type === 'password' }"
            stroke-width="2"
          />
        </div>
        <input
          :value="modelValue"
          :type="inputType"
          :autocomplete="autocomplete"
          :placeholder="placeholder"
          class="auth-field-input min-h-[46px] flex-1 border-0 bg-transparent px-2 py-3 text-sm text-slate-900 outline-none ring-0 placeholder:text-gray-400 focus:outline-none focus:ring-0 dark:text-white dark:placeholder:text-slate-500 sm:px-3"
          :class="inputClass"
          @input="onInput"
          @focus="focused = true"
          @blur="focused = false"
          @keyup.enter="emit('enter')"
        />
        <button
          v-if="type === 'password'"
          type="button"
          class="flex shrink-0 items-center pr-3 text-gray-400 transition-all hover:scale-105 hover:text-sky-600 active:rotate-180 dark:text-slate-500 dark:hover:text-sky-400"
          tabindex="-1"
          aria-label="切换密码可见性"
          @click="showPassword = !showPassword"
        >
          <EyeOff v-if="showPassword" :size="18" class="transition-transform duration-300" />
          <Eye v-else :size="18" class="transition-transform duration-300" />
        </button>
      </div>
    </div>
    <p
      v-if="error"
      class="mt-1 pl-0.5 text-xs text-rose-500 dark:text-rose-300"
      role="alert"
    >
      {{ error }}
    </p>
  </div>
</template>

<style scoped>
.auth-field-input:focus-visible {
  outline: none;
}

.auth-field:focus-within .auth-field-input:focus-visible {
  box-shadow: 0 0 0 4px rgba(165, 180, 252, 0.12);
  border-radius: 0.35rem;
}

.auth-field-input:-webkit-autofill,
.auth-field-input:-webkit-autofill:hover,
.auth-field-input:-webkit-autofill:focus {
  -webkit-text-fill-color: rgb(15 23 42);
  transition: background-color 99999s ease-out;
  box-shadow: 0 0 0 1000px rgba(224, 242, 254, 0.45) inset !important;
}

:global(html.dark) .auth-field-input:-webkit-autofill,
:global(html.dark) .auth-field-input:-webkit-autofill:hover,
:global(html.dark) .auth-field-input:-webkit-autofill:focus {
  -webkit-text-fill-color: rgba(255, 255, 255, 0.95);
  box-shadow: 0 0 0 1000px rgba(30, 41, 59, 0.85) inset !important;
}
</style>
