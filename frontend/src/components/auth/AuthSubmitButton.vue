<script setup lang="ts">
import { ref } from 'vue'
import { Sparkles, ArrowRight } from 'lucide-vue-next'

const props = withDefaults(
  defineProps<{
    loading?: boolean
    disabled?: boolean
  }>(),
  { loading: false, disabled: false },
)

const ripples = ref<{ x: number; y: number; id: number }[]>([])
let rippleId = 0

function onPointerDown(e: PointerEvent) {
  if (props.loading || props.disabled) return
  const el = e.currentTarget as HTMLElement
  const r = el.getBoundingClientRect()
  const id = ++rippleId
  ripples.value.push({
    id,
    x: e.clientX - r.left,
    y: e.clientY - r.top,
  })
  window.setTimeout(() => {
    ripples.value = ripples.value.filter((x) => x.id !== id)
  }, 600)
}
</script>

<template>
  <button
    type="submit"
    class="auth-submit touch-manipulation select-none"
    :class="{ 'auth-submit--loading': loading }"
    :disabled="disabled || loading"
    @pointerdown="onPointerDown"
  >
    <span class="auth-submit__pulse" aria-hidden="true" />
    <span class="auth-submit__breath" aria-hidden="true" />
    <span class="auth-submit__shine" aria-hidden="true" />
    <span class="auth-submit__corner auth-submit__corner--tl" aria-hidden="true" />
    <span class="auth-submit__corner auth-submit__corner--br" aria-hidden="true" />

    <span
      v-for="rp in ripples"
      :key="rp.id"
      class="pointer-events-none absolute z-[3] h-20 w-20 rounded-full bg-white/25"
      :style="{
        left: `${rp.x}px`,
        top: `${rp.y}px`,
        animation: 'auth-ripple-expand 0.55s ease-out forwards',
      }"
      aria-hidden="true"
    />

    <span class="auth-submit__content">
      <Sparkles
        v-if="!loading"
        :size="18"
        class="shrink-0 opacity-95"
        stroke-width="2.2"
        aria-hidden="true"
      />
      <span v-if="loading" class="auth-submit__loader shrink-0" aria-hidden="true" />
      <span><slot /></span>
      <ArrowRight v-if="!loading" :size="18" class="auth-submit__arrow shrink-0 opacity-95" stroke-width="2.2" aria-hidden="true" />
    </span>
  </button>
</template>

<style scoped>
@keyframes auth-ripple-expand {
  0% {
    transform: translate(-50%, -50%) scale(0.15);
    opacity: 0.5;
  }
  100% {
    transform: translate(-50%, -50%) scale(3);
    opacity: 0;
  }
}
</style>
