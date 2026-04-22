<template>
  <div
    class="blob-root fixed inset-0 overflow-hidden pointer-events-none z-0"
    :class="prefersReducedMotion ? 'blob-reduced' : ''"
    aria-hidden="true"
  >
    <!-- Light: layered ambient -->
    <div class="blob-base-light dark:hidden" />
    <div class="blob-pattern-dots dark:hidden" />
    <div class="blob-pattern-diagonal dark:hidden" />

    <!-- Large floating orbs (light) -->
    <div class="blob-orb blob-orb--amber dark:hidden" />
    <div class="blob-orb blob-orb--sky dark:hidden" />
    <div class="blob-orb blob-orb--rose dark:hidden" />
    <div class="blob-orb blob-orb--teal dark:hidden" />

    <!-- Gradient wave strips (light) -->
    <div class="blob-wave blob-wave--amber dark:hidden" />
    <div class="blob-wave blob-wave--sky dark:hidden" />

    <!-- Particles (light) -->
    <div
      v-for="n in 12"
      :key="n"
      class="blob-particle dark:hidden"
      :class="`blob-particle--${((n - 1) % 4) + 1}`"
      :style="{ '--d': `${(n - 1) * 0.35}s`, '--x': `${8 + (n * 7) % 86}%`, '--s': `${0.35 + (n % 5) * 0.06}` }"
    />

    <!-- Dark mode: keep softer motion -->
    <div class="hidden dark:block absolute top-[-10%] left-[-10%] w-[40vw] h-[40vw] rounded-full bg-blue-300/20 dark:bg-indigo-600/15 filter blur-3xl animate-blob" />
    <div class="hidden dark:block absolute top-[20%] right-[-10%] w-[35vw] h-[35vw] rounded-full bg-indigo-200/30 dark:bg-fuchsia-600/15 filter blur-3xl animate-blob animation-delay-2000" />
    <div class="hidden dark:block absolute bottom-[-20%] left-[20%] w-[50vw] h-[50vw] rounded-full bg-cyan-200/30 dark:bg-cyan-600/10 filter blur-3xl animate-blob animation-delay-4000" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'

const prefersReducedMotion = ref(false)
let mq: MediaQueryList | null = null

function readMotion() {
  prefersReducedMotion.value = window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches ?? false
}

onMounted(() => {
  readMotion()
  mq = window.matchMedia?.('(prefers-reduced-motion: reduce)') ?? null
  mq?.addEventListener('change', readMotion)
})

onBeforeUnmount(() => {
  mq?.removeEventListener('change', readMotion)
})
</script>

<style scoped>
.blob-root {
  contain: strict;
}

.blob-reduced .blob-orb,
.blob-reduced .blob-wave,
.blob-reduced .blob-particle {
  animation: none !important;
}

/* Soft base wash */
.blob-base-light {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    125deg,
    rgba(255, 247, 237, 0.45) 0%,
    rgba(255, 255, 255, 0.92) 42%,
    rgba(240, 249, 255, 0.5) 100%
  );
  opacity: 1;
}

.blob-pattern-dots {
  position: absolute;
  inset: 0;
  background-image: radial-gradient(rgba(15, 23, 42, 0.006) 1px, transparent 1px);
  background-size: 28px 28px;
  opacity: 0.85;
}

.blob-pattern-diagonal {
  position: absolute;
  inset: 0;
  background-image: repeating-linear-gradient(
    -32deg,
    transparent,
    transparent 14px,
    rgba(59, 130, 246, 0.004) 14px,
    rgba(59, 130, 246, 0.004) 15px
  );
  opacity: 0.9;
}

.blob-orb {
  position: absolute;
  border-radius: 9999px;
  filter: blur(64px);
  opacity: 0.36;
  will-change: transform;
  animation: blob-drift 24s ease-in-out infinite alternate;
}

.blob-orb--amber {
  width: min(720px, 85vw);
  height: min(720px, 85vw);
  top: -12%;
  left: -18%;
  background: radial-gradient(circle at 30% 30%, rgba(251, 191, 36, 0.55), rgba(253, 186, 116, 0.2) 60%, transparent 70%);
  animation-delay: 0s;
}
.blob-orb--sky {
  width: min(640px, 78vw);
  height: min(640px, 78vw);
  top: 8%;
  right: -14%;
  background: radial-gradient(circle at 40% 40%, rgba(56, 189, 248, 0.5), rgba(125, 211, 252, 0.22) 58%, transparent 72%);
  animation-delay: -4s;
}
.blob-orb--rose {
  width: min(560px, 70vw);
  height: min(560px, 70vw);
  bottom: -8%;
  left: 10%;
  background: radial-gradient(circle at 50% 50%, rgba(244, 114, 182, 0.45), rgba(251, 207, 232, 0.2) 55%, transparent 70%);
  animation-delay: -8s;
}
.blob-orb--teal {
  width: min(680px, 80vw);
  height: min(680px, 80vw);
  bottom: -18%;
  right: -10%;
  background: radial-gradient(circle at 35% 35%, rgba(45, 212, 191, 0.42), rgba(153, 246, 228, 0.18) 60%, transparent 72%);
  animation-delay: -12s;
}

@keyframes blob-drift {
  0% {
    transform: translate3d(0, 0, 0) scale(1);
  }
  100% {
    transform: translate3d(24px, -32px, 0) scale(1.06);
  }
}

.blob-wave {
  position: absolute;
  left: -20%;
  width: 140%;
  height: 120px;
  border-radius: 9999px;
  filter: blur(40px);
  opacity: 0.26;
  will-change: transform;
  animation: wave-x 22s linear infinite;
}

.blob-wave--amber {
  top: 38%;
  background: linear-gradient(90deg, transparent, rgba(251, 191, 36, 0.35), rgba(253, 186, 116, 0.25), transparent);
  animation-duration: 26s;
}
.blob-wave--sky {
  top: 62%;
  background: linear-gradient(90deg, transparent, rgba(125, 211, 252, 0.4), rgba(56, 189, 248, 0.22), transparent);
  animation-duration: 19s;
  animation-direction: reverse;
}

@keyframes wave-x {
  0% {
    transform: translate3d(-8%, 0, 0);
  }
  100% {
    transform: translate3d(8%, 0, 0);
  }
}

.blob-particle {
  position: absolute;
  bottom: -4%;
  left: var(--x);
  width: calc(6px * var(--s));
  height: calc(6px * var(--s));
  border-radius: 9999px;
  opacity: 0.38;
  will-change: transform, opacity;
  animation: particle-rise 18s ease-in-out infinite;
  animation-delay: var(--d);
}

.blob-particle--1 {
  background: linear-gradient(180deg, rgba(251, 191, 36, 0.85), rgba(253, 186, 116, 0.35));
}
.blob-particle--2 {
  background: linear-gradient(180deg, rgba(56, 189, 248, 0.85), rgba(125, 211, 252, 0.35));
}
.blob-particle--3 {
  background: linear-gradient(180deg, rgba(244, 114, 182, 0.85), rgba(251, 207, 232, 0.35));
}
.blob-particle--4 {
  background: linear-gradient(180deg, rgba(45, 212, 191, 0.85), rgba(153, 246, 228, 0.35));
}

@keyframes particle-rise {
  0% {
    transform: translate3d(0, 0, 0);
    opacity: 0;
  }
  12% {
    opacity: 0.42;
  }
  100% {
    transform: translate3d(calc(var(--s) * -18px), -88vh, 0);
    opacity: 0;
  }
}
</style>
