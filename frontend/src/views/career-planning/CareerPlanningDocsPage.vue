<script setup lang="ts">
import { BookOpen, Clock3, Library } from 'lucide-vue-next'
import CareerDocsPanel from '../../components/career-planning/CareerDocsPanel.vue'
import { useCareerPlanningStore } from '../../stores/careerPlanning'
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

const store = useCareerPlanningStore()
const route = useRoute()

// Phase 4: 资源闭环 → 任务页跳转到指定 doc + section。
// 通过 query.doc_id / query.section_idx 解析，并在 docs 加载完成后下钻。
const pendingDocId = ref<string>('')
const pendingSectionIdx = ref<number>(0)
const pendingReason = ref<string>('')

onMounted(() => {
  // 如果文档还没有加载，则加载
  if (!store.documents.length && !store.docsLoading) {
    store.loadDocs()
  }

  // 解析路由 query：来自任务卡 / 资源推荐区
  const docId = typeof route.query.doc_id === 'string' ? route.query.doc_id.trim() : ''
  const sectionRaw = typeof route.query.section_idx === 'string' ? route.query.section_idx : '0'
  const reason = typeof route.query.reason === 'string' ? route.query.reason : ''
  const sectionIdx = Number.parseInt(sectionRaw, 10)
  if (docId) {
    pendingDocId.value = docId
    pendingSectionIdx.value = Number.isFinite(sectionIdx) ? sectionIdx : 0
    pendingReason.value = reason
  }
})

// 文档加载完毕后，把下钻意图下发给 CareerDocsPanel
function handleDocsLoaded() {
  if (!pendingDocId.value) return
  // 仅当下钻目标在当前文档集中时下发；否则保留在 pending，下一次加载后再生效
  if (store.documents.some((d) => d.id === pendingDocId.value)) {
    jumpToSectionRef.value?.(pendingDocId.value, pendingSectionIdx.value)
    pendingDocId.value = ''
    pendingReason.value = ''
  }
}

const jumpToSectionRef = ref<((docId: string, sectionIdx: number) => void) | null>(null)

function registerJumpToSection(fn: (docId: string, sectionIdx: number) => void) {
  jumpToSectionRef.value = fn
  handleDocsLoaded()
}
</script>

<template>
  <section class="career-docs-page space-y-4">
    <div class="career-docs-page__hero ui-card">
      <div>
        <span class="ui-section-badge">学习中心</span>
        <h2 class="ui-page-title mt-4 text-3xl">把职业规划资料集中到一个可检索的文档库</h2>
        <p class="ui-page-subtitle mt-3 max-w-2xl text-sm leading-7">
          从求职指南到 AI 面试技巧，再到职业发展路径，这里把学习内容集中成统一的资料面板，方便查阅和回看。
        </p>
        <p
          v-if="pendingReason"
          class="career-docs-page__hint mt-3 inline-flex items-center gap-1 rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-700 dark:border-indigo-500/40 dark:bg-indigo-500/15 dark:text-indigo-200"
        >
          🎯 来自任务推荐：{{ pendingReason }}
        </p>
      </div>

      <div class="career-docs-page__stats">
        <div class="career-docs-page__stat">
          <div class="career-docs-page__stat-icon">
            <Library class="h-4 w-4" />
          </div>
          <div>
            <span class="career-docs-page__stat-label">文档数量</span>
            <strong class="career-docs-page__stat-value">{{ store.documents.length }}</strong>
          </div>
        </div>

        <div class="career-docs-page__stat">
          <div class="career-docs-page__stat-icon">
            <BookOpen class="h-4 w-4" />
          </div>
          <div>
            <span class="career-docs-page__stat-label">加载状态</span>
            <strong class="career-docs-page__stat-value">{{ store.docsLoading ? '加载中' : '已就绪' }}</strong>
          </div>
        </div>

        <div class="career-docs-page__stat">
          <div class="career-docs-page__stat-icon">
            <Clock3 class="h-4 w-4" />
          </div>
          <div>
            <span class="career-docs-page__stat-label">阅读方式</span>
            <strong class="career-docs-page__stat-value">集中查阅</strong>
          </div>
        </div>
      </div>
    </div>

    <CareerDocsPanel
      :documents="store.documents"
      :loading="store.docsLoading"
      :error="store.docsError"
      @retry="store.loadDocs({ force: true })"
      @register-jump="registerJumpToSection"
    />
  </section>
</template>

<style scoped>
.career-docs-page__hero {
  position: relative;
  overflow: hidden;
  display: grid;
  gap: 1rem;
  padding: 1.6rem;
}

.career-docs-page__hero::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 14% 18%, rgba(59, 130, 246, 0.14), transparent 28%),
    radial-gradient(circle at 88% 22%, rgba(99, 102, 241, 0.1), transparent 24%);
  pointer-events: none;
}

.career-docs-page__stats {
  position: relative;
  z-index: 1;
  display: grid;
  gap: 0.75rem;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.career-docs-page__stat {
  display: flex;
  align-items: center;
  gap: 0.8rem;
  border-radius: 1.2rem;
  border: 1px solid var(--ui-border-subtle);
  background: var(--ui-surface-raised);
  padding: 1rem;
  box-shadow: var(--ui-shadow-sm);
}

.career-docs-page__stat-icon {
  display: inline-flex;
  width: 2.5rem;
  height: 2.5rem;
  align-items: center;
  justify-content: center;
  border-radius: 0.95rem;
  background: rgba(59, 130, 246, 0.12);
  color: var(--ui-accent-strong);
  flex-shrink: 0;
}

.career-docs-page__stat-label {
  display: block;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ui-text-muted);
}

.career-docs-page__stat-value {
  display: block;
  margin-top: 0.4rem;
  font-size: 1.1rem;
  font-weight: 900;
  color: var(--ui-text-primary);
}

.dark .career-docs-page__stat {
  background: rgba(15, 23, 42, 0.72);
}

@media (max-width: 960px) {
  .career-docs-page__stats {
    grid-template-columns: 1fr;
  }
}
</style>
