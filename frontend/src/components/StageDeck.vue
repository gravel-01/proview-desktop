<script setup lang="ts">
import { computed } from 'vue'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'

interface StageDeckItem {
  id: string
}

type StageDeckRenderableItem = StageDeckItem & Record<string, unknown>

const props = withDefaults(defineProps<{
  items: StageDeckItem[]
  modelValue: string
  expanded?: boolean
  showArrows?: boolean
  cardWidth?: number
  cardHeight?: number
  cardRadius?: number
}>(), {
  expanded: false,
  showArrows: true,
  cardWidth: 292,
  cardHeight: 216,
  cardRadius: 28,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const normalizedItems = computed(() => props.items as StageDeckRenderableItem[])

const selectedIndex = computed(() => {
  const index = normalizedItems.value.findIndex(item => item.id === props.modelValue)
  return index >= 0 ? index : 0
})

const stageStyle = computed(() => ({
  '--deck-card-width': `${props.cardWidth}px`,
  '--deck-card-height': `${props.cardHeight}px`,
  '--deck-card-radius': `${props.cardRadius}px`,
}))

function updateSelection(nextIndex: number) {
  const nextItem = normalizedItems.value[nextIndex]
  if (!nextItem) return
  emit('update:modelValue', nextItem.id)
}

function getRelativeOffset(index: number) {
  const total = normalizedItems.value.length
  if (!total) return 0

  let offset = index - selectedIndex.value
  if (offset > total / 2) offset -= total
  if (offset < -total / 2) offset += total
  return offset
}

function getCardState(index: number) {
  if (props.expanded) return 'grid'

  const offset = getRelativeOffset(index)
  if (offset === 0) return 'active'
  if (offset === -1) return 'prev'
  if (offset === 1) return 'next'
  return offset < 0 ? 'hidden-left' : 'hidden-right'
}

function selectCard(id: string) {
  if (!id || id === props.modelValue) return
  emit('update:modelValue', id)
}

function prevCard() {
  if (normalizedItems.value.length <= 1) return
  const total = normalizedItems.value.length
  const nextIndex = (selectedIndex.value - 1 + total) % total
  updateSelection(nextIndex)
}

function nextCard() {
  if (normalizedItems.value.length <= 1) return
  const total = normalizedItems.value.length
  const nextIndex = (selectedIndex.value + 1) % total
  updateSelection(nextIndex)
}
</script>

<template>
  <div class="stage-deck" :style="stageStyle">
    <button
      v-if="showArrows && !expanded && normalizedItems.length > 1"
      type="button"
      class="stage-deck__nav stage-deck__nav--left"
      aria-label="上一张卡片"
      @click="prevCard"
    >
      <ChevronLeft class="h-5 w-5" />
    </button>

    <button
      v-if="showArrows && !expanded && normalizedItems.length > 1"
      type="button"
      class="stage-deck__nav stage-deck__nav--right"
      aria-label="下一张卡片"
      @click="nextCard"
    >
      <ChevronRight class="h-5 w-5" />
    </button>

    <div
      class="stage-deck__viewport"
      :class="expanded ? 'stage-deck__viewport--grid' : 'stage-deck__viewport--carousel'"
    >
      <button
        v-for="(item, index) in normalizedItems"
        :key="item.id"
        type="button"
        class="stage-deck__card-wrap"
        :class="[
          `stage-deck__card-wrap--${getCardState(index)}`,
          item.id === modelValue ? 'stage-deck__card-wrap--selected' : ''
        ]"
        :aria-pressed="item.id === modelValue"
        @click="selectCard(item.id)"
      >
        <article
          class="stage-deck__card"
          :class="[
            item.id === modelValue ? 'stage-deck__card--active' : 'stage-deck__card--idle',
            expanded ? 'stage-deck__card--expanded' : ''
          ]"
        >
          <slot
            name="card"
            :item="item"
            :active="item.id === modelValue"
            :expanded="expanded"
            :position="getCardState(index)"
          >
            <div class="stage-deck__fallback">
              <strong>{{ item.id }}</strong>
            </div>
          </slot>
        </article>
      </button>
    </div>
  </div>
</template>

<style scoped>
.stage-deck {
  position: relative;
}

.stage-deck__viewport {
  width: 100%;
}

.stage-deck__viewport--carousel {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: calc(var(--deck-card-height) + 40px);
  perspective: 1200px;
}

.stage-deck__viewport--grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr));
  gap: 1.5rem;
}

.stage-deck__card-wrap {
  transition:
    transform 320ms cubic-bezier(0.4, 0, 0.2, 1),
    opacity 320ms cubic-bezier(0.4, 0, 0.2, 1),
    filter 320ms cubic-bezier(0.4, 0, 0.2, 1),
    z-index 320ms ease;
}

.stage-deck__viewport--carousel .stage-deck__card-wrap {
  position: absolute;
  left: 50%;
  top: 50%;
  width: var(--deck-card-width);
  height: var(--deck-card-height);
  margin-left: calc(var(--deck-card-width) / -2);
  margin-top: calc(var(--deck-card-height) / -2);
}

.stage-deck__viewport--grid .stage-deck__card-wrap {
  position: relative;
  width: 100%;
  min-height: var(--deck-card-height);
}

.stage-deck__card-wrap--active {
  z-index: 30;
  opacity: 1;
  transform: translate3d(0, 0, 0) scale(1);
}

.stage-deck__card-wrap--prev {
  z-index: 20;
  opacity: 0.5;
  transform: translate3d(calc(var(--deck-card-width) * -0.6), 0, -20px) scale(0.85);
}

.stage-deck__card-wrap--next {
  z-index: 20;
  opacity: 0.5;
  transform: translate3d(calc(var(--deck-card-width) * 0.6), 0, -20px) scale(0.85);
}

.stage-deck__card-wrap--hidden-left {
  z-index: 10;
  opacity: 0;
  transform: translate3d(calc(var(--deck-card-width) * -1), 0, -48px) scale(0.7);
  pointer-events: none;
}

.stage-deck__card-wrap--hidden-right {
  z-index: 10;
  opacity: 0;
  transform: translate3d(calc(var(--deck-card-width) * 1), 0, -48px) scale(0.7);
  pointer-events: none;
}

.stage-deck__card-wrap--grid {
  opacity: 1;
  transform: none;
}

.stage-deck__card {
  width: 100%;
  min-height: 100%;
  padding: 1rem;
  border-radius: var(--deck-card-radius);
  border: 1px solid rgba(226, 232, 240, 0.88);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.9) 0%, rgba(248, 250, 252, 0.94) 100%);
  box-shadow:
    0 24px 48px rgba(15, 23, 42, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.72);
  text-align: left;
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  transition:
    transform 220ms ease,
    border-color 220ms ease,
    box-shadow 220ms ease,
    background-color 220ms ease;
}

.stage-deck__card-wrap:hover .stage-deck__card,
.stage-deck__card--active {
  border-color: rgba(129, 140, 248, 0.4);
  box-shadow:
    0 26px 56px rgba(79, 70, 229, 0.12),
    inset 0 1px 0 rgba(255, 255, 255, 0.74);
}

.stage-deck__card-wrap:hover .stage-deck__card {
  transform: translateY(-2px);
}

.stage-deck__card--expanded {
  min-height: var(--deck-card-height);
}

.stage-deck__nav {
  position: absolute;
  top: 50%;
  z-index: 40;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 3rem;
  height: 3rem;
  border: 1px solid rgba(226, 232, 240, 0.92);
  border-radius: 9999px;
  background: rgba(255, 255, 255, 0.86);
  color: #475569;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
  transform: translateY(-50%);
  transition:
    transform 180ms ease,
    border-color 180ms ease,
    color 180ms ease,
    background-color 180ms ease;
}

.stage-deck__nav:hover {
  transform: translateY(-50%) scale(1.03);
  border-color: rgba(129, 140, 248, 0.44);
  color: #4338ca;
  background: rgba(255, 255, 255, 0.96);
}

.stage-deck__nav--left {
  left: 0;
}

.stage-deck__nav--right {
  right: 0;
}

.stage-deck__fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: calc(var(--deck-card-height) - 2rem);
  color: #0f172a;
}

:global(html.dark) .stage-deck__card {
  border-color: rgba(255, 255, 255, 0.08);
  background:
    linear-gradient(180deg, rgba(11, 14, 24, 0.94) 0%, rgba(8, 11, 19, 0.96) 100%);
  box-shadow:
    0 24px 48px rgba(0, 0, 0, 0.34),
    inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

:global(html.dark) .stage-deck__card-wrap:hover .stage-deck__card,
:global(html.dark) .stage-deck__card--active {
  border-color: rgba(129, 140, 248, 0.3);
  box-shadow:
    0 24px 52px rgba(0, 0, 0, 0.4),
    0 0 0 1px rgba(129, 140, 248, 0.18);
}

:global(html.dark) .stage-deck__nav {
  border-color: rgba(255, 255, 255, 0.08);
  background: rgba(15, 23, 42, 0.82);
  color: #cbd5e1;
}

:global(html.dark) .stage-deck__nav:hover {
  border-color: rgba(129, 140, 248, 0.28);
  color: #c4b5fd;
  background: rgba(30, 41, 59, 0.92);
}

@media (max-width: 768px) {
  .stage-deck__viewport--carousel .stage-deck__card-wrap {
    width: min(100%, var(--deck-card-width));
    margin-left: calc(min(100%, var(--deck-card-width)) / -2);
  }

  .stage-deck__card-wrap--prev {
    transform: translate3d(calc(var(--deck-card-width) * -0.45), 0, -20px) scale(0.85);
  }

  .stage-deck__card-wrap--next {
    transform: translate3d(calc(var(--deck-card-width) * 0.45), 0, -20px) scale(0.85);
  }

  .stage-deck__nav {
    display: none;
  }
}
</style>
