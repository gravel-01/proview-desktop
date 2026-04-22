<script setup lang="ts">
import { ref } from 'vue'
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
const loading = ref(false)
const error = ref('')
const usernameErr = ref('')
const passwordErr = ref('')

async function handleLogin() {
  error.value = ''
  usernameErr.value = ''
  passwordErr.value = ''
  if (!username.value.trim()) usernameErr.value = '请输入用户名'
  if (!password.value) passwordErr.value = '请输入密码'
  if (usernameErr.value || passwordErr.value) return

  loading.value = true
  try {
    await auth.login(username.value.trim(), password.value)
    router.push('/')
  } catch (e: unknown) {
    const err = e as { response?: { data?: { message?: string } } }
    error.value = err.response?.data?.message || '登录失败，请检查用户名和密码'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <AuthPageScaffold subtitle="欢迎回来！">
    <form class="space-y-5" @submit.prevent="handleLogin">
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
        placeholder="请输入用户名"
        type="text"
        autocomplete="username"
        required
        :icon="Mail"
        :error="usernameErr"
      />

      <AuthTextField
        v-model="password"
        label="密码"
        placeholder="请输入密码"
        type="password"
        autocomplete="current-password"
        required
        :icon="Lock"
        :error="passwordErr"
        @enter="handleLogin"
      />

      <div class="pt-1">
        <AuthSubmitButton :loading="loading">
          {{ loading ? '登录中...' : '登录' }}
        </AuthSubmitButton>
      </div>

      <div class="auth-divider" aria-hidden="true" />

      <p class="text-center text-sm text-gray-400 dark:text-slate-500">
        还没有账号？
        <router-link to="/register" class="auth-link-gradient">注册</router-link>
      </p>
    </form>
  </AuthPageScaffold>
</template>
