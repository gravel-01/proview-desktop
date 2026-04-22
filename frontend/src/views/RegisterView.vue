<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { Mail, Lock, XCircle } from 'lucide-vue-next'
import AuthPageScaffold from '../components/auth/AuthPageScaffold.vue'
import AuthTextField from '../components/auth/AuthTextField.vue'
import AuthSubmitButton from '../components/auth/AuthSubmitButton.vue'

const router = useRouter()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const error = ref('')
const usernameErr = ref('')
const passwordErr = ref('')
const confirmErr = ref('')

const strength = computed(() => {
  const p = password.value
  if (!p) {
    return { level: -1 as const, label: '', pct: 0, color: '#e5e7eb' }
  }
  let score = 0
  if (p.length >= 6) score++
  if (p.length >= 9) score++
  if (/\d/.test(p)) score++
  if (/[a-z]/.test(p) && /[A-Z]/.test(p)) score++
  if (/[^A-Za-z0-9]/.test(p)) score++

  if (score <= 1) {
    return { level: 0 as const, label: '弱', pct: 33, color: '#fb7185' }
  }
  if (score <= 3) {
    return { level: 1 as const, label: '中', pct: 66, color: '#f59e0b' }
  }
  return { level: 2 as const, label: '强', pct: 100, color: '#34d399' }
})

async function handleRegister() {
  error.value = ''
  usernameErr.value = ''
  passwordErr.value = ''
  confirmErr.value = ''

  if (!username.value.trim()) usernameErr.value = '请输入用户名'
  if (!password.value) passwordErr.value = '请输入密码'
  else if (password.value.length < 6) passwordErr.value = '密码至少 6 个字符'
  if (!confirmPassword.value) confirmErr.value = '请再次输入密码'
  else if (password.value !== confirmPassword.value) confirmErr.value = '两次密码不一致'

  if (usernameErr.value || passwordErr.value || confirmErr.value) return

  loading.value = true
  try {
    await auth.register(username.value.trim(), password.value)
    router.push('/navigation-preferences?from=register')
  } catch (e: unknown) {
    const err = e as { response?: { data?: { message?: string } } }
    error.value = err.response?.data?.message || '注册失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <AuthPageScaffold subtitle="创建新账号">
    <form class="space-y-5" @submit.prevent="handleRegister">
      <div
        v-if="error"
        class="auth-alert auth-alert--error"
        role="alert"
      >
        <XCircle class="mt-0.5 h-4 w-4 shrink-0 text-rose-500" aria-hidden="true" />
        <span>{{ error }}</span>
      </div>

      <AuthTextField
        v-model="username"
        label="用户名"
        placeholder="至少 2 个字符"
        type="text"
        autocomplete="username"
        required
        :icon="Mail"
        :error="usernameErr"
      />

      <div>
        <AuthTextField
          v-model="password"
          label="密码"
          placeholder="至少 6 个字符"
          type="password"
          autocomplete="new-password"
          required
          :icon="Lock"
          :error="passwordErr"
        />
        <div v-if="password && !passwordErr" class="mt-2">
          <div class="auth-strength-track">
            <div
              class="auth-strength-fill"
              :style="{
                width: `${strength.pct}%`,
                backgroundColor: strength.color,
              }"
            />
          </div>
          <p class="mt-1 text-xs font-medium" :style="{ color: strength.color }">
            密码强度：{{ strength.label }}
          </p>
        </div>
      </div>

      <AuthTextField
        v-model="confirmPassword"
        label="确认密码"
        placeholder="再次输入密码"
        type="password"
        autocomplete="new-password"
        required
        :icon="Lock"
        :error="confirmErr"
        @enter="handleRegister"
      />

      <div class="pt-1">
        <AuthSubmitButton :loading="loading">
          {{ loading ? '注册中...' : '注册' }}
        </AuthSubmitButton>
      </div>

      <div class="auth-divider" aria-hidden="true" />

      <p class="text-center text-sm text-gray-400 dark:text-slate-500">
        已有账号？
        <router-link to="/login" class="auth-link-gradient">登录</router-link>
      </p>
    </form>
  </AuthPageScaffold>
</template>
