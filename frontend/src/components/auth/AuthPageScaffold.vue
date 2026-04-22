<script setup lang="ts">
import { ref, computed } from 'vue'

defineProps<{
  subtitle: string
}>()

const tiltRx = ref(0)
const tiltRy = ref(0)

const tiltStyle = computed(() => ({
  transform: `perspective(880px) rotateX(${tiltRx.value}deg) rotateY(${tiltRy.value}deg)`,
}))

function onCardMove(e: MouseEvent) {
  const t = e.currentTarget as HTMLElement
  const r = t.getBoundingClientRect()
  const x = (e.clientX - r.left) / r.width - 0.5
  const y = (e.clientY - r.top) / r.height - 0.5
  tiltRy.value = x * 6
  tiltRx.value = y * -6
}

function onCardLeave() {
  tiltRx.value = 0
  tiltRy.value = 0
}

const particlePalette = ['#fbbf24', '#38bdf8', '#fb7185', '#22d3ee'] as const

const particles = [
  { left: '7%', top: '18%', delay: 0, dur: 14, px: 48, py: -190, py2: -240, c: 0 },
  { left: '18%', top: '72%', delay: 0.4, dur: 22, px: -72, py: -160, py2: -210, c: 1 },
  { left: '88%', top: '12%', delay: 0.8, dur: 18, px: -55, py: -220, py2: -260, c: 2 },
  { left: '92%', top: '58%', delay: 1.2, dur: 16, px: 60, py: -150, py2: -200, c: 3 },
  { left: '42%', top: '8%', delay: 1.6, dur: 26, px: -40, py: -270, py2: -200, c: 0 },
  { left: '55%', top: '88%', delay: 2, dur: 12, px: 70, py: -170, py2: -230, c: 1 },
  { left: '28%', top: '44%', delay: 2.4, dur: 20, px: -65, py: -200, py2: -250, c: 2 },
  { left: '72%', top: '38%', delay: 2.8, dur: 17, px: 45, py: -180, py2: -220, c: 3 },
  { left: '12%', top: '52%', delay: 3.2, dur: 24, px: 80, py: -210, py2: -260, c: 0 },
  { left: '78%', top: '78%', delay: 3.6, dur: 15, px: -50, py: -165, py2: -200, c: 1 },
  { left: '50%', top: '28%', delay: 4, dur: 19, px: 35, py: -240, py2: -180, c: 2 },
  { left: '65%', top: '62%', delay: 4.4, dur: 21, px: -85, py: -195, py2: -245, c: 3 },
]
</script>

<template>
  <div
    class="relative min-h-screen overflow-x-hidden bg-gradient-to-br from-orange-50/30 via-white to-sky-50/30 dark:from-slate-950 dark:via-slate-900 dark:to-indigo-950/50"
  >
    <div class="auth-orb auth-orb--tl" aria-hidden="true" />
    <div class="auth-orb auth-orb--tr" aria-hidden="true" />
    <div class="auth-orb auth-orb--bl" aria-hidden="true" />
    <div class="auth-orb auth-orb--cr" aria-hidden="true" />

    <div class="auth-wave-layer" aria-hidden="true">
      <div class="auth-wave-strip" />
    </div>
    <div class="auth-wave-layer auth-wave-layer--reverse" aria-hidden="true">
      <div class="auth-wave-strip" />
    </div>

    <div
      v-for="(p, i) in particles"
      :key="i"
      class="auth-particle"
      :style="{
        left: p.left,
        top: p.top,
        '--delay': `${p.delay}s`,
        '--dur': `${p.dur}s`,
        '--px': `${p.px}px`,
        '--py': `${p.py}px`,
        '--py2': `${p.py2}px`,
        backgroundColor: particlePalette[p.c],
      }"
      aria-hidden="true"
    />

    <div class="auth-pattern-dots" aria-hidden="true" />
    <div class="auth-pattern-lines" aria-hidden="true" />
    <div class="auth-radial-veil" aria-hidden="true" />

    <div class="relative z-10 flex min-h-screen items-center justify-center px-3 py-10 sm:px-4 sm:py-12">
      <div class="auth-card-wrap w-full min-w-[min(100%,320px)] sm:min-w-0">
        <div class="auth-card-glow-ring" aria-hidden="true" />
        <div class="auth-card-inner-glow" aria-hidden="true" />

        <div class="auth-card-enter-anim">
          <div
            class="auth-card-tilt-layer"
            :style="tiltStyle"
            @mousemove="onCardMove"
            @mouseleave="onCardLeave"
          >
            <div class="auth-card-float-layer">
              <div class="auth-card-surface">
                <div class="mb-8 text-center sm:mb-9">
                  <h1 class="text-2xl font-bold tracking-tight text-sky-600 dark:text-sky-400 sm:text-[1.65rem]">
                    ProView AI
                  </h1>
                  <p class="auth-subtitle-anim mt-2 text-sm text-gray-500 dark:text-slate-400">
                    {{ subtitle }}
                  </p>
                </div>

                <slot />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
