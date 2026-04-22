<script setup lang="ts">
import CareerDocsPanel from '../../components/career-planning/CareerDocsPanel.vue'
import { useCareerPlanningStore } from '../../stores/careerPlanning'
import { onMounted } from 'vue'

const store = useCareerPlanningStore()

onMounted(() => {
  // 如果文档还没有加载，则加载
  if (!store.documents.length && !store.docsLoading) {
    store.loadDocs()
  }
})
</script>

<template>
  <section class="space-y-4">
    <!-- 页面介绍卡片 -->
    <div
      class="ui-card rounded-3xl border border-gray-200/60 bg-[linear-gradient(135deg,rgba(224,242,254,0.5)_0%,rgba(219,234,254,0.6)_50%,rgba(255,255,255,0.8)_100%)] p-6 shadow-[0_8px_24px_rgba(59,130,246,0.06)] dark:border-white/10 dark:bg-[linear-gradient(135deg,rgba(15,23,42,0.9)_0%,rgba(30,41,59,0.86)_48%,rgba(15,23,42,0.92)_100%)]"
    >
      <div class="flex items-start justify-between">
        <div>
          <p class="text-xs font-semibold uppercase tracking-wider text-blue-800/80 dark:text-blue-200/80">学习中心</p>
          <h2 class="mt-2 text-2xl font-black text-blue-900 dark:text-blue-100">ProView AI 面试学习资源库</h2>
          <p class="mt-2 max-w-2xl text-sm leading-relaxed text-blue-800/80 dark:text-slate-300">
            从求职指南到AI面试技巧，从职业规划到发展路径——我们为你在每个阶段准备了最实用的学习资源。
            每份文档都配有可执行的行动项，帮助你将知识转化为实际行动。
          </p>
        </div>
        <div class="hidden md:flex shrink-0">
          <div class="flex -space-x-3">
            <div class="h-10 w-10 rounded-full bg-sky-100 flex items-center justify-center text-lg dark:bg-sky-500/20">🎯</div>
            <div class="h-10 w-10 rounded-full bg-blue-100 flex items-center justify-center text-lg dark:bg-blue-500/20">📊</div>
            <div class="h-10 w-10 rounded-full bg-white flex items-center justify-center text-lg border border-blue-200/60 dark:border-blue-400/30 dark:bg-white/10">🚀</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 文档库组件 -->
    <CareerDocsPanel 
      :documents="store.documents" 
      :loading="store.docsLoading" 
      :error="store.docsError" 
      @retry="store.loadDocs({ force: true })"
    />
  </section>
</template>
