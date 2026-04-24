<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowLeft,
  AudioLines,
  Bot,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  Image,
  KeyRound,
  RefreshCw,
  Settings,
  ShieldCheck,
  UserRound,
  Waypoints,
  X,
} from 'lucide-vue-next'
import { useAuthStore } from '../stores/auth'
import {
  describeRuntimeApiBaseUrl,
  fetchRuntimeConfig,
  getRuntimeApiBaseUrl,
  probeApiHealth,
  saveRuntimeConfig,
  setRuntimeApiBaseUrl,
  type RuntimeConfigResponse,
} from '../services/runtimeConfig'

type RuntimeFormKey =
  | 'apiBaseUrl'
  | 'LOCAL_USER_NAME'
  | 'DEEPSEEK_BASE_URL'
  | 'DEEPSEEK_API_KEY'
  | 'ERNIE_BASE_URL'
  | 'ERNIE_API_KEY'
  | 'PADDLEOCR_API_URL'
  | 'PADDLE_OCR_TOKEN'
  | 'BAIDU_APP_KEY'
  | 'BAIDU_SECRET_KEY'

type SecretFieldKey =
  | 'PADDLEOCR_API_URL'
  | 'DEEPSEEK_API_KEY'
  | 'ERNIE_API_KEY'
  | 'PADDLE_OCR_TOKEN'
  | 'BAIDU_APP_KEY'
  | 'BAIDU_SECRET_KEY'

interface FieldMeta {
  key: RuntimeFormKey
  label: string
  placeholder: string
  description: string
}

interface GuideStep {
  id: string
  title: string
  caption: string
  image: string
  alt: string
  fields?: string[]
}

interface GuidePanel {
  eyebrow: string
  title: string
  summary: string
  steps: GuideStep[]
  tips: string[]
  secondaryCard?: {
    title: string
    description: string
    image?: string
    alt?: string
    fields?: string[]
  }
}

type SettingsPanelId = 'identity' | 'models' | 'ocr' | 'speech'

const router = useRouter()
const auth = useAuthStore()

const loading = ref(true)
const saving = ref(false)
const probing = ref(false)
const error = ref('')
const success = ref('')
const probeMessage = ref('')
const probeStatus = ref<'idle' | 'success' | 'error'>('idle')
const settingsNotesOpen = ref(false)
const guideDialogOpen = ref(false)
const guideImageViewerOpen = ref(false)
const envFilePath = ref('')
const speechAvailable = ref(false)
const models = ref<Array<{ key: string; label: string; available: boolean }>>([])
const activeBackendBase = ref(getRuntimeApiBaseUrl())
const backendConfigLoaded = ref(false)
const guideViewerImage = reactive({
  src: '',
  alt: '',
  title: '',
})
const guideStepIndex = reactive<Record<SettingsPanelId, number>>({
  identity: 0,
  models: 0,
  ocr: 0,
  speech: 0,
})

const form = reactive<Record<RuntimeFormKey, string>>({
  apiBaseUrl: getRuntimeApiBaseUrl(),
  LOCAL_USER_NAME: '',
  DEEPSEEK_BASE_URL: '',
  DEEPSEEK_API_KEY: '',
  ERNIE_BASE_URL: '',
  ERNIE_API_KEY: '',
  PADDLEOCR_API_URL: '',
  PADDLE_OCR_TOKEN: '',
  BAIDU_APP_KEY: '',
  BAIDU_SECRET_KEY: '',
})

const configured = reactive<Record<string, boolean>>({})
const displayValues = reactive<Record<string, string>>({})
const clearSecretFlags = reactive<Record<SecretFieldKey, boolean>>({
  PADDLEOCR_API_URL: false,
  DEEPSEEK_API_KEY: false,
  ERNIE_API_KEY: false,
  PADDLE_OCR_TOKEN: false,
  BAIDU_APP_KEY: false,
  BAIDU_SECRET_KEY: false,
})

const profileFields: FieldMeta[] = [
  {
    key: 'LOCAL_USER_NAME',
    label: '本机用户名',
    placeholder: '例如：张三 / 前端调试机',
    description: '单机模式下显示在界面右上角、历史记录和本地工作区中的名称。',
  },
]

const networkFields: FieldMeta[] = [
  {
    key: 'apiBaseUrl',
    label: '前端 API_URL',
    placeholder: '留空则使用同源地址 / 桌面版内置地址',
    description: '控制前端请求发往哪个后端服务，保存后后续请求立即生效。',
  },
  {
    key: 'DEEPSEEK_BASE_URL',
    label: 'DeepSeek API_URL',
    placeholder: 'https://api.deepseek.com/v1',
    description: '兼容 OpenAI 协议的模型网关地址。',
  },
  {
    key: 'ERNIE_BASE_URL',
    label: '文心 API_URL',
    placeholder: 'https://aistudio.baidu.com/llm/lmapi/v3',
    description: '百度文心模型调用地址。',
  },
]

const secretFields: Array<FieldMeta & { key: SecretFieldKey }> = [
  {
    key: 'PADDLEOCR_API_URL',
    label: 'PaddleOCR API_URL',
    placeholder: '留空表示保持现有值',
    description: 'OCR 服务地址，作为私密配置由用户在本机自行注入。',
  },
  {
    key: 'DEEPSEEK_API_KEY',
    label: 'DeepSeek API_KEY',
    placeholder: '留空表示保持现有值',
    description: '用于 DeepSeek 模型调用。',
  },
  {
    key: 'ERNIE_API_KEY',
    label: '文心 API_KEY',
    placeholder: '留空表示保持现有值',
    description: '用于百度文心模型调用。',
  },
  {
    key: 'PADDLE_OCR_TOKEN',
    label: 'PaddleOCR Token',
    placeholder: '留空表示保持现有值',
    description: '用于 OCR 服务鉴权。',
  },
  {
    key: 'BAIDU_APP_KEY',
    label: '百度语音 App Key',
    placeholder: '留空表示保持现有值',
    description: '用于语音识别 / 语音合成。',
  },
  {
    key: 'BAIDU_SECRET_KEY',
    label: '百度语音 Secret Key',
    placeholder: '留空表示保持现有值',
    description: '与 App Key 配套使用。',
  },
]

const currentApiBaseLabel = computed(() => describeRuntimeApiBaseUrl(form.apiBaseUrl))
const activeBackendLabel = computed(() => describeRuntimeApiBaseUrl(activeBackendBase.value))
const activePanel = ref<SettingsPanelId>('identity')
const availableModelCount = computed(() => models.value.filter(model => model.available).length)
const configuredSecretCount = computed(() => secretFields.filter(field => configured[field.key]).length)
const ocrConfigured = computed(() => !!(configured.PADDLEOCR_API_URL || configured.PADDLE_OCR_TOKEN))
const speechConfigured = computed(() => speechAvailable.value || !!(configured.BAIDU_APP_KEY || configured.BAIDU_SECRET_KEY))
const identityFields = computed(() => profileFields)
const connectionFields = computed(() => networkFields.filter(field => field.key === 'apiBaseUrl'))
const modelNetworkFields = computed(() => networkFields.filter(field => (
  field.key === 'DEEPSEEK_BASE_URL' || field.key === 'ERNIE_BASE_URL'
)))
const modelSecretFields = computed(() => secretFields.filter(field => (
  field.key === 'DEEPSEEK_API_KEY' || field.key === 'ERNIE_API_KEY'
)))
const ocrSecretFields = computed(() => secretFields.filter(field => (
  field.key === 'PADDLEOCR_API_URL' || field.key === 'PADDLE_OCR_TOKEN'
)))
const speechSecretFields = computed(() => secretFields.filter(field => (
  field.key === 'BAIDU_APP_KEY' || field.key === 'BAIDU_SECRET_KEY'
)))
const settingsPanels = computed(() => [
  {
    id: 'identity' as const,
    eyebrow: '基础控制',
    title: '本机与连接',
    description: '统一维护本机用户身份和前端 API 入口，保证页面右上角与请求入口保持一致。',
    indicator: currentApiBaseLabel.value,
  },
  {
    id: 'models' as const,
    eyebrow: 'LLM 接入',
    title: '模型服务',
    description: '集中配置 DeepSeek 与文心的网关地址、密钥和模型接入入口。',
    indicator: `${availableModelCount.value} / ${models.value.length || 0} 模型可用`,
  },
  {
    id: 'ocr' as const,
    eyebrow: 'OCR 接入',
    title: 'OCR 配置',
    description: '单独维护 OCR 的服务地址与鉴权 Token，避免和语音或模型配置混在一起。',
    indicator: ocrConfigured.value ? 'OCR 已配置' : 'OCR 待配置',
  },
  {
    id: 'speech' as const,
    eyebrow: '语音接入',
    title: '语音配置',
    description: '单独维护百度语音 App Key 与 Secret Key，让语音能力成为一张独立配置卡。',
    indicator: speechConfigured.value ? '语音已配置' : '语音待配置',
  },
])
const panelIcons: Record<SettingsPanelId, typeof UserRound> = {
  identity: UserRound,
  models: Bot,
  ocr: ShieldCheck,
  speech: AudioLines,
}

const settingsPanelFallback = {
  id: 'identity' as const,
  eyebrow: '基础控制',
  title: '本机与连接',
  description: '统一维护本机用户身份和前端 API 入口，保证页面右上角与请求入口保持一致。',
  indicator: '',
}

const guideAsset = (filename: string) => `/runtime-guides/${filename}`

const settingsGuideMap: Record<SettingsPanelId, GuidePanel> = {
  identity: {
    eyebrow: '上手引导',
    title: '先进入，再填写，再保存',
    summary: '这一张卡负责带用户找到应用设置入口、进入工作台，并完成本机名称与 API 入口的首次填写。',
    steps: [
      {
        id: 'entry',
        title: '从左下角进入应用设置',
        caption: '首次使用时，先在左下角找到“应用设置”入口，进入单机版运行时配置页。',
        image: guideAsset('a34a74a26bdc69786975818666062ea.png'),
        alt: '应用设置入口引导图',
        fields: ['应用设置入口'],
      },
      {
        id: 'panel',
        title: '确认当前工作台位置',
        caption: '进入后先确认自己处于应用设置工作台，后续的模型、OCR 和语音都会在这里统一维护。',
        image: guideAsset('92477119f37d0c60e745d545b6f0add.png'),
        alt: '应用设置面板引导图',
        fields: ['工作台位置', '运行状态'],
      },
      {
        id: 'save',
        title: '填写后点击保存配置',
        caption: '本机用户名和前端 API_URL 填好后，统一从页面下方保存，不需要分开提交。',
        image: guideAsset('3254ba8d88e69408c205b660fca4ab6.png'),
        alt: '密钥填写与保存位置引导图',
        fields: ['LOCAL_USER_NAME', 'apiBaseUrl', '保存配置'],
      },
    ],
    tips: [
      '单机版默认不需要登录，本机用户名会显示在右上角和本地工作区。',
      '前端 API_URL 保存后会立即影响后续请求入口。',
      '如果当前后端未连通，页面仍然会先保存 API_URL 到本地。',
    ],
  },
  models: {
    eyebrow: '模型接入',
    title: '文心跟图走，DeepSeek 用默认网关',
    summary: '模型服务卡片内直接展示文心获取 API 的操作链路；DeepSeek 没有仓库截图，所以用默认地址和字段映射提示补足。',
    steps: [
      {
        id: 'ernie-entry',
        title: '进入文心模型体验区',
        caption: '先登录百度 AI Studio，进入模型体验或模型广场，准备切到 API 模式。',
        image: guideAsset('b35fb4a1d85ddd0c136ff0576648402.png'),
        alt: '文心模型体验区入口图',
        fields: ['ERNIE_BASE_URL', 'ERNIE_API_KEY'],
      },
      {
        id: 'ernie-api',
        title: '切换到 API 页面',
        caption: '不要停留在编辑视图，切到 API 页签后才能看到真实可复制的接入地址和密钥。',
        image: guideAsset('e6da98d1e8ba5e54598a5651d16c2ee.png'),
        alt: '文心 API 页签引导图',
        fields: ['API 页签'],
      },
      {
        id: 'ernie-copy',
        title: '复制 API Key 和 Base URL',
        caption: '把截图里高亮的 key 和 base_url 一一对应填回当前工作台中的文心字段。',
        image: guideAsset('dd5906b528b5a1a3981d4dab872adc3.png'),
        alt: '复制文心接口密钥引导图',
        fields: ['ERNIE_API_KEY', 'ERNIE_BASE_URL'],
      },
    ],
    tips: [
      '文心字段对应 `ERNIE_BASE_URL` 和 `ERNIE_API_KEY`。',
      'DeepSeek 默认网关通常直接填 `https://api.deepseek.com/v1`。',
      '密钥输入框留空不会覆盖旧值，只有填写新值或勾选清空才会更新。',
    ],
    secondaryCard: {
      title: 'DeepSeek 快速填写',
      description: 'DeepSeek 没有放仓库截图，这里直接给出最短路径：填默认网关，再填你购买得到的 API Key 即可。',
      fields: ['DEEPSEEK_BASE_URL', 'DEEPSEEK_API_KEY', 'https://api.deepseek.com/v1'],
    },
  },
  ocr: {
    eyebrow: 'OCR 接入',
    title: 'OCR 配置教程',
    summary: 'OCR 的 API_URL 和 Token 单独跟着这组引导图填写，完成后直接回到 OCR 配置卡保存即可。',
    steps: [
      {
        id: 'ocr-entry',
        title: '进入 PaddleOCR 服务页',
        caption: '先进入 PaddleOCR 页面，找到服务入口，再准备切到 API 模式。',
        image: guideAsset('4834759d1a2534a8e0992130f4e5bbe.png'),
        alt: '进入 PaddleOCR 服务页面引导图',
        fields: ['PADDLEOCR_API_URL', 'PADDLE_OCR_TOKEN'],
      },
      {
        id: 'ocr-api',
        title: '切到 OCR 的 API 入口',
        caption: '在服务页中进入 API 调用入口，避免只停留在体验页看不到真正的接入参数。',
        image: guideAsset('7763155a127dba1e1c9ae56555b822d.png'),
        alt: '查看 OCR 配置入口引导图',
        fields: ['OCR API 入口'],
      },
      {
        id: 'ocr-copy',
        title: '复制 OCR URL 与 Token',
        caption: '把高亮区域里的 API_URL 和 TOKEN 分别填回当前工作台的 OCR 两个字段。',
        image: guideAsset('7c5854ad6c8bdbe4e8ddfd16d8877b1.png'),
        alt: '复制 OCR 密钥引导图',
        fields: ['PADDLEOCR_API_URL', 'PADDLE_OCR_TOKEN'],
      },
    ],
    tips: [
      '如果 OCR 服务指向本机或局域网地址，VPN 全局模式可能影响连通性。',
      'OCR 字段只对应 `PADDLEOCR_API_URL` 与 `PADDLE_OCR_TOKEN`。',
      '留空不覆盖原值，勾选清空后才会真正把原有密钥删除。',
    ],
  },
  speech: {
    eyebrow: '语音接入',
    title: '百度语音配置教程',
    summary: '语音配置拆成独立卡片后，教程也单独查看。先按图完成申请与实名认证，再把 App Key 和 Secret Key 回填到语音配置卡。',
    steps: [
      {
        id: 'speech-entry',
        title: '查看百度语音接入说明',
        caption: '先按说明图完成百度语音服务的开通、应用创建与认证，再回到当前配置卡填写 App Key 和 Secret Key。',
        image: guideAsset('2d1dd3681f5008c54576049f0eb89c8.png'),
        alt: '百度语音配置说明引导图',
        fields: ['BAIDU_APP_KEY', 'BAIDU_SECRET_KEY'],
      },
    ],
    tips: [
      '语音配置只对应 `BAIDU_APP_KEY` 与 `BAIDU_SECRET_KEY` 两个字段。',
      '语音能力是否可用，仍然由现有后端探测逻辑决定。',
      '留空不覆盖原值，勾选清空后才会真正删除语音密钥。',
    ],
  },
}

const settingsNotes = [
  '单机版默认使用当前设备上的一个本地用户，不再需要登录或注册。',
  '前端 API_URL 存在浏览器本地存储里，修改后新的请求会立刻走新地址。',
  '模型与 OCR 密钥会写入后端运行时 .env，后端会同步刷新可用模型列表。',
  '如果你想恢复默认开发模式，把前端 API_URL 清空即可。',
  '桌面版运行时会把配置写入 Electron 用户数据目录中的 backend-data/.env。',
]

const activeSettingsPanelInfo = computed(() => (
  settingsPanels.value.find(panel => panel.id === activePanel.value) || settingsPanels.value[0] || settingsPanelFallback
))

const activeGuide = computed(() => settingsGuideMap[activePanel.value])
const activeGuideTrackStyle = computed(() => ({
  transform: `translateX(-${(guideStepIndex[activePanel.value] || 0) * 100}%)`,
}))
const canPrevGuideStep = computed(() => (guideStepIndex[activePanel.value] || 0) > 0)
const canNextGuideStep = computed(() => {
  const steps = activeGuide.value.steps
  return (guideStepIndex[activePanel.value] || 0) < Math.max(steps.length - 1, 0)
})

const runtimeOverviewItems = computed(() => [
  { label: '本机用户', value: form.LOCAL_USER_NAME || '本地用户' },
  { label: 'Env File', value: envFilePath.value || '未读取到' },
  { label: '后端配置', value: backendConfigLoaded.value ? '已加载后端配置' : '当前未连通后端' },
  { label: '已配置密钥', value: String(configuredSecretCount.value) },
])

function setGuideStep(panel: SettingsPanelId, index: number) {
  guideStepIndex[panel] = index
}

function openGuideDialog() {
  guideDialogOpen.value = true
}

function closeGuideDialog() {
  guideDialogOpen.value = false
}

function prevGuideStep() {
  if (!canPrevGuideStep.value) return
  setGuideStep(activePanel.value, (guideStepIndex[activePanel.value] || 0) - 1)
}

function nextGuideStep() {
  if (!canNextGuideStep.value) return
  setGuideStep(activePanel.value, (guideStepIndex[activePanel.value] || 0) + 1)
}

function openGuideImage(image: string, alt: string, title: string) {
  guideViewerImage.src = image
  guideViewerImage.alt = alt
  guideViewerImage.title = title
  guideImageViewerOpen.value = true
}

function closeGuideImage() {
  guideImageViewerOpen.value = false
}

function goBack() {
  router.push('/')
}

function applySnapshot(snapshot: RuntimeConfigResponse) {
  envFilePath.value = snapshot.env_file_path || ''
  speechAvailable.value = !!snapshot.speech_available
  models.value = Array.isArray(snapshot.models) ? snapshot.models : []
  form.LOCAL_USER_NAME = snapshot.fields?.LOCAL_USER_NAME?.value || '本地用户'
  configured.LOCAL_USER_NAME = !!snapshot.fields?.LOCAL_USER_NAME?.configured
  displayValues.LOCAL_USER_NAME = snapshot.fields?.LOCAL_USER_NAME?.display_value || form.LOCAL_USER_NAME

  for (const field of networkFields) {
    if (field.key === 'apiBaseUrl') {
      continue
    }
    const nextValue = snapshot.fields?.[field.key]?.value || ''
    form[field.key] = nextValue
    configured[field.key] = !!snapshot.fields?.[field.key]?.configured
    displayValues[field.key] = snapshot.fields?.[field.key]?.display_value || nextValue
  }

  for (const field of secretFields) {
    form[field.key] = ''
    configured[field.key] = !!snapshot.fields?.[field.key]?.configured
    displayValues[field.key] = snapshot.fields?.[field.key]?.display_value || ''
    clearSecretFlags[field.key] = false
  }
}

async function loadConfig() {
  loading.value = true
  error.value = ''
  try {
    activeBackendBase.value = getRuntimeApiBaseUrl()
    form.apiBaseUrl = getRuntimeApiBaseUrl()
    const snapshot = await fetchRuntimeConfig(activeBackendBase.value)
    applySnapshot(snapshot)
    backendConfigLoaded.value = true
  } catch (err) {
    backendConfigLoaded.value = false
    error.value = err instanceof Error ? err.message : '读取配置失败'
  } finally {
    loading.value = false
  }
}

async function handleProbeApi() {
  probing.value = true
  probeMessage.value = ''
  probeStatus.value = 'idle'

  try {
    await probeApiHealth(form.apiBaseUrl)
    probeStatus.value = 'success'
    probeMessage.value = `连接成功：${currentApiBaseLabel.value}`
  } catch (err) {
    probeStatus.value = 'error'
    probeMessage.value = err instanceof Error ? err.message : '连接失败'
  } finally {
    probing.value = false
  }
}

async function handleSave() {
  saving.value = true
  error.value = ''
  success.value = ''
  let apiUrlPersisted = false

  try {
    const previousBase = getRuntimeApiBaseUrl()
    const nextApiBase = setRuntimeApiBaseUrl(form.apiBaseUrl)
    apiUrlPersisted = previousBase !== nextApiBase
    activeBackendBase.value = nextApiBase
    form.apiBaseUrl = nextApiBase

    if (!backendConfigLoaded.value) {
      success.value = 'API_URL 已保存。当前后端未连通，本机用户名、密钥与网关地址尚未写入后端 .env。'
      return
    }

    const payload: Record<string, string> = {
      LOCAL_USER_NAME: form.LOCAL_USER_NAME.trim(),
      DEEPSEEK_BASE_URL: form.DEEPSEEK_BASE_URL.trim(),
      ERNIE_BASE_URL: form.ERNIE_BASE_URL.trim(),
    }

    for (const field of secretFields) {
      const nextValue = form[field.key].trim()
      if (clearSecretFlags[field.key]) {
        payload[field.key] = ''
      } else if (nextValue) {
        payload[field.key] = nextValue
      }
    }

    const snapshot = await saveRuntimeConfig(payload, previousBase)
    applySnapshot(snapshot)
    await auth.tryRestore()
    success.value = snapshot.message || '应用设置已保存'
  } catch (err) {
    const message = err instanceof Error ? err.message : '保存失败'
    error.value = apiUrlPersisted
      ? `${message}；前端 API_URL 已更新`
      : message
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadConfig()
})
</script>

<template>
  <div class="settings-shell mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
    <section class="settings-hero">
      <div class="settings-hero__copy">
        <div class="settings-hero__badge">
          <Settings class="h-3.5 w-3.5" />
          Application Settings
        </div>
        <h1>应用设置工作台</h1>
        <p>
          这里是单机版的统一设置入口。保留现有配置字段、保存逻辑和 API 探测逻辑，只把填写流程重构成“前面先看运行状态、下面再按步骤填写、教程按需弹出查看”的工作台。
        </p>
        <div class="settings-hero__meta">
          <span class="settings-hero__meta-chip">
            <Waypoints class="h-4 w-4 text-sky-500" />
            {{ activeBackendLabel }}
          </span>
          <span class="settings-hero__meta-chip">
            <Bot class="h-4 w-4 text-indigo-500" />
            {{ availableModelCount }} / {{ models.length || 0 }} 个模型可用
          </span>
          <span class="settings-hero__meta-chip">
            <AudioLines class="h-4 w-4 text-emerald-500" />
            {{ speechAvailable ? '语音能力已接通' : '语音能力待配置' }}
          </span>
        </div>
      </div>
      <button type="button" class="settings-ghost-btn shrink-0" @click="goBack">
        <ArrowLeft class="h-4 w-4" />
        返回
      </button>
    </section>

    <div class="mt-8">
      <section class="settings-workbench">
        <div class="settings-workbench__top">
          <div>
            <p class="settings-section-eyebrow">Edit Deck</p>
            <h2>配置编辑台</h2>
            <p>保留原有字段、保存逻辑和 API 探测逻辑，把当前配置面板重构成“左侧填写、右侧看图引导、下方看运行状态”的单工作台布局。</p>
          </div>
          <button type="button" class="settings-ghost-btn" :disabled="loading" @click="loadConfig">
            <RefreshCw class="h-4 w-4" :class="{ 'animate-spin': loading }" />
            刷新配置
          </button>
        </div>

        <div v-if="error" class="settings-alert settings-alert--error">
          {{ error }}
        </div>
        <div v-if="success" class="settings-alert settings-alert--success">
          {{ success }}
        </div>

        <section class="settings-runtime-hub">
          <div class="settings-runtime-hub__head">
            <div>
              <p class="settings-section-eyebrow">Runtime Board</p>
              <h3>运行状态工作台</h3>
              <p>先看当前运行状态，再进入下面的配置编辑台。这里压成两个组件：左侧是更大的运行概览，右侧是压缩后的模型、OCR 与语音能力状态。</p>
            </div>
            <div class="settings-runtime-hub__actions">
              <span class="settings-inline-badge">
                <CheckCircle2 class="h-3.5 w-3.5" />
                Live
              </span>
              <button type="button" class="settings-ghost-btn" :disabled="loading" @click="loadConfig">
                <RefreshCw class="h-4 w-4" :class="{ 'animate-spin': loading }" />
                刷新配置
              </button>
            </div>
          </div>

          <div class="settings-runtime-hub__grid">
            <section class="settings-runtime-hub__section settings-runtime-hub__section--overview">
              <div class="settings-dashboard-card__head">
                <div>
                  <p class="settings-section-eyebrow">Dashboard</p>
                  <h4>运行概览</h4>
                  <p>把运行仪表盘和运行环境合在一起，只保留本机用户、配置文件、后端加载状态和密钥总量这些真正需要对照的信息。</p>
                </div>
              </div>
              <div class="settings-metric-grid settings-metric-grid--overview">
                <article v-for="item in runtimeOverviewItems" :key="item.label" class="settings-metric settings-metric--overview">
                  <span class="settings-metric__label">{{ item.label }}</span>
                  <strong class="settings-metric__value">{{ item.value }}</strong>
                </article>
              </div>
            </section>

            <section class="settings-runtime-hub__section settings-runtime-hub__section--status">
              <div class="settings-dashboard-card__head">
                <div>
                  <p class="settings-section-eyebrow">Capability Status</p>
                  <h4>能力状态</h4>
                  <p>把大模型情况、OCR 状态和语音状态压缩进一个更窄的状态卡里，方便填写后快速确认接入是否生效。</p>
                </div>
              </div>

              <div class="settings-runtime-status">
                <div class="settings-runtime-status__summary">
                  <article class="settings-runtime-status__tile">
                    <span class="settings-metric__label">大模型</span>
                    <strong class="settings-metric__value">{{ availableModelCount }} / {{ models.length || 0 }} 可用</strong>
                  </article>
                  <article class="settings-runtime-status__tile">
                    <span class="settings-metric__label">OCR</span>
                    <strong class="settings-metric__value">{{ ocrConfigured ? '已配置' : '待配置' }}</strong>
                  </article>
                  <article class="settings-runtime-status__tile">
                    <span class="settings-metric__label">语音</span>
                    <strong class="settings-metric__value">{{ speechConfigured ? '已配置' : '待配置' }}</strong>
                  </article>
                </div>

                <div class="settings-runtime-status__models">
                  <div class="settings-runtime-status__models-head">
                    <span class="settings-section-eyebrow">Model List</span>
                    <span class="settings-inline-badge">
                      <Bot class="h-3.5 w-3.5" />
                      {{ models.length || 0 }} 项
                    </span>
                  </div>
                  <div class="space-y-2.5">
                    <div v-for="model in models" :key="model.key" class="settings-runtime-status__model-row">
                      <div class="min-w-0">
                        <div class="truncate font-semibold text-slate-800 dark:text-slate-100">{{ model.label }}</div>
                        <div class="truncate text-[11px] text-slate-500 dark:text-slate-400">{{ model.key }}</div>
                      </div>
                      <span class="settings-status-chip" :class="model.available ? 'settings-status-chip--success' : 'settings-status-chip--warning'">
                        {{ model.available ? '可用' : '未配置' }}
                      </span>
                    </div>
                    <div v-if="!models.length" class="settings-model-empty">
                      尚未读取到模型状态。
                    </div>
                  </div>
                </div>
              </div>
            </section>
          </div>
        </section>

        <section class="settings-editor-card">
          <div class="settings-editor-card__head">
            <div>
              <p class="settings-section-eyebrow">{{ activeSettingsPanelInfo.eyebrow }}</p>
              <h3>{{ activeSettingsPanelInfo.title }}</h3>
              <p>{{ activeSettingsPanelInfo.description }} 当前顶部只保留轻量步骤导航，下面一次只显示一张主配置卡；教程会按当前卡片单独弹出查看。</p>
            </div>
            <div class="settings-editor-card__actions">
              <span v-if="activeSettingsPanelInfo.indicator" class="settings-stage__badge">{{ activeSettingsPanelInfo.indicator }}</span>
              <button type="button" class="settings-secondary-btn" @click="openGuideDialog">
                <Image class="h-4 w-4" />
                查看教程
              </button>
            </div>
          </div>

          <div class="settings-step-nav">
            <button
              v-for="(panel, index) in settingsPanels"
              :key="panel.id"
              type="button"
              class="settings-step-nav__item"
              :class="activePanel === panel.id ? 'settings-step-nav__item--active' : ''"
              @click="activePanel = panel.id"
            >
              <span class="settings-step-nav__lead">
                <span class="settings-step-nav__index">{{ index + 1 }}</span>
                <span class="settings-step-nav__icon">
                  <component :is="panelIcons[panel.id]" class="h-4 w-4" />
                </span>
              </span>
              <span class="settings-step-nav__copy">
                <strong>{{ panel.title }}</strong>
                <span>{{ panel.description }}</span>
              </span>
              <span class="settings-step-nav__state">{{ activePanel === panel.id ? '当前步骤' : panel.indicator }}</span>
            </button>
          </div>

          <div class="settings-editor-card__body">
            <div class="settings-editor-card__form">
              <template v-if="activePanel === 'identity'">
                <article class="settings-config-card">
                  <div class="settings-config-card__summary">
                    <p class="settings-config-card__note">第一张卡只负责本机身份与前端连接。先确认当前单机用户名，再决定前端请求入口，保存后后续请求会立即切换。</p>
                    <span class="settings-inline-badge">基础配置卡</span>
                  </div>
                  <div class="settings-config-card__grid settings-config-card__grid--two">
                    <section class="settings-config-card__block">
                      <div class="settings-form-card__head">
                        <div class="settings-form-card__icon">
                          <UserRound class="h-4 w-4" />
                        </div>
                        <div>
                          <p class="settings-form-card__eyebrow">Local Profile</p>
                          <h4 class="settings-form-card__title">本机身份</h4>
                          <p class="settings-form-card__desc">单机模式下显示在右上角、历史记录和本地工作区里的默认名称。</p>
                        </div>
                      </div>
                      <div class="space-y-4">
                        <div v-for="field in identityFields" :key="field.key">
                          <label :for="field.key" class="settings-label">{{ field.label }}</label>
                          <p class="settings-helper">{{ field.description }}</p>
                          <input
                            :id="field.key"
                            v-model="form[field.key]"
                            type="text"
                            class="settings-input"
                            :placeholder="field.placeholder"
                          />
                          <div class="mt-3">
                            <span class="settings-status-chip settings-status-chip--neutral">
                              当前显示：{{ displayValues.LOCAL_USER_NAME || form.LOCAL_USER_NAME || '本地用户' }}
                            </span>
                          </div>
                        </div>
                      </div>
                    </section>

                    <section class="settings-config-card__block">
                      <div class="settings-form-card__head">
                        <div class="settings-form-card__icon">
                          <Waypoints class="h-4 w-4" />
                        </div>
                        <div>
                          <p class="settings-form-card__eyebrow">Connection</p>
                          <h4 class="settings-form-card__title">前端 API_URL</h4>
                          <p class="settings-form-card__desc">保存后后续请求会立即切到新地址，同时保留当前 API 健康检查逻辑。</p>
                        </div>
                      </div>
                      <div class="space-y-4">
                        <div v-for="field in connectionFields" :key="field.key">
                          <label :for="field.key" class="settings-label">{{ field.label }}</label>
                          <p class="settings-helper">{{ field.description }}</p>
                          <input
                            :id="field.key"
                            v-model="form[field.key]"
                            type="text"
                            class="settings-input"
                            :placeholder="field.placeholder"
                          />
                          <div class="mt-3 flex flex-wrap items-center gap-3">
                            <span class="settings-status-chip settings-status-chip--neutral">当前保存值：{{ currentApiBaseLabel }}</span>
                            <span class="settings-status-chip settings-status-chip--neutral">当前运行地址：{{ activeBackendLabel }}</span>
                            <button type="button" class="settings-secondary-btn" :disabled="probing" @click="handleProbeApi">
                              {{ probing ? '检测中...' : '检测 API 连通性' }}
                            </button>
                          </div>
                        </div>
                      </div>
                    </section>
                  </div>
                </article>
              </template>

              <template v-else-if="activePanel === 'models'">
                <article class="settings-config-card">
                  <div class="settings-config-card__summary">
                    <p class="settings-config-card__note">模型服务卡把网关地址和密钥放在同一张步骤卡里，填写顺序建议先地址后密钥。DeepSeek 和文心仍然沿用当前保存逻辑。</p>
                    <span class="settings-inline-badge">{{ availableModelCount }} / {{ models.length || 0 }} 模型可用</span>
                  </div>
                  <div class="settings-config-card__grid settings-config-card__grid--two">
                    <section class="settings-config-card__block">
                      <div class="settings-form-card__head">
                        <div class="settings-form-card__icon">
                          <Bot class="h-4 w-4" />
                        </div>
                        <div>
                          <p class="settings-form-card__eyebrow">Gateway</p>
                          <h4 class="settings-form-card__title">模型网关地址</h4>
                          <p class="settings-form-card__desc">先把 DeepSeek 和文心的请求入口确定下来，再填写对应密钥。</p>
                        </div>
                      </div>
                      <div class="space-y-4">
                        <div v-for="field in modelNetworkFields" :key="field.key">
                          <label :for="field.key" class="settings-label">{{ field.label }}</label>
                          <p class="settings-helper">{{ field.description }}</p>
                          <input
                            :id="field.key"
                            v-model="form[field.key]"
                            type="text"
                            class="settings-input"
                            :placeholder="field.placeholder"
                          />
                        </div>
                      </div>
                    </section>

                    <section class="settings-config-card__block">
                      <div class="settings-form-card__head">
                        <div class="settings-form-card__icon">
                          <KeyRound class="h-4 w-4" />
                        </div>
                        <div>
                          <p class="settings-form-card__eyebrow">Secret</p>
                          <h4 class="settings-form-card__title">模型 API Key</h4>
                          <p class="settings-form-card__desc">密钥留空不会覆盖旧值，只有填写新值或勾选清空才会更新。</p>
                        </div>
                      </div>
                      <div class="space-y-4">
                        <div v-for="field in modelSecretFields" :key="field.key" class="settings-sensitive-item">
                          <label :for="field.key" class="settings-label">{{ field.label }}</label>
                          <p class="settings-helper">{{ field.description }}</p>
                          <div v-if="configured[field.key]" class="settings-status-chip settings-status-chip--neutral">
                            当前值：{{ displayValues[field.key] || '已配置' }}
                          </div>
                          <input
                            :id="field.key"
                            v-model="form[field.key]"
                            type="password"
                            class="settings-input"
                            :placeholder="field.placeholder"
                          />
                          <label class="settings-toggle">
                            <input v-model="clearSecretFlags[field.key]" type="checkbox" class="settings-toggle__input" />
                            清空这个密钥
                          </label>
                        </div>
                      </div>
                    </section>
                  </div>
                </article>
              </template>

              <template v-else-if="activePanel === 'ocr'">
                <article class="settings-config-card">
                  <div class="settings-config-card__summary">
                    <p class="settings-config-card__note">OCR 现在是一张独立卡片，只维护服务地址和 Token。跟着 OCR 教程填完后，这张卡里就能单独保存和回查状态。</p>
                    <span class="settings-inline-badge">{{ ocrConfigured ? 'OCR 已配置' : 'OCR 待配置' }}</span>
                  </div>
                  <section class="settings-config-card__block">
                    <div class="settings-form-card__head">
                      <div class="settings-form-card__icon">
                        <ShieldCheck class="h-4 w-4" />
                      </div>
                      <div>
                        <p class="settings-form-card__eyebrow">OCR Service</p>
                        <h4 class="settings-form-card__title">OCR 服务</h4>
                        <p class="settings-form-card__desc">保留原有掩码展示与清空逻辑，但从现在开始，OCR 和语音彻底拆开配置。</p>
                      </div>
                    </div>
                    <div class="space-y-4">
                      <div v-for="field in ocrSecretFields" :key="field.key" class="settings-sensitive-item">
                        <label :for="field.key" class="settings-label">{{ field.label }}</label>
                        <p class="settings-helper">{{ field.description }}</p>
                        <div v-if="configured[field.key]" class="settings-status-chip settings-status-chip--neutral">
                          当前值：{{ displayValues[field.key] || '已配置' }}
                        </div>
                        <input
                          :id="field.key"
                          v-model="form[field.key]"
                          type="password"
                          class="settings-input"
                          :placeholder="field.placeholder"
                        />
                        <label class="settings-toggle">
                          <input v-model="clearSecretFlags[field.key]" type="checkbox" class="settings-toggle__input" />
                          清空这个密钥
                        </label>
                      </div>
                    </div>
                  </section>
                </article>
              </template>

              <template v-else>
                <article class="settings-config-card">
                  <div class="settings-config-card__summary">
                    <p class="settings-config-card__note">语音配置也拆成独立卡片，只保留百度语音的两个关键字段。填写方式更接近面试配置抽屉里的步骤卡，但不直接照搬样式。</p>
                    <span class="settings-inline-badge">{{ speechConfigured ? '语音已配置' : '语音待配置' }}</span>
                  </div>
                  <section class="settings-config-card__block">
                    <div class="settings-form-card__head">
                      <div class="settings-form-card__icon">
                        <AudioLines class="h-4 w-4" />
                      </div>
                      <div>
                        <p class="settings-form-card__eyebrow">Speech Stack</p>
                        <h4 class="settings-form-card__title">语音能力</h4>
                        <p class="settings-form-card__desc">用于语音识别和语音合成的鉴权信息，保存后仍由现有后端逻辑写入运行时 `.env`。</p>
                      </div>
                    </div>
                    <div class="space-y-4">
                      <div v-for="field in speechSecretFields" :key="field.key" class="settings-sensitive-item">
                        <label :for="field.key" class="settings-label">{{ field.label }}</label>
                        <p class="settings-helper">{{ field.description }}</p>
                        <div v-if="configured[field.key]" class="settings-status-chip settings-status-chip--neutral">
                          当前值：{{ displayValues[field.key] || '已配置' }}
                        </div>
                        <input
                          :id="field.key"
                          v-model="form[field.key]"
                          type="password"
                          class="settings-input"
                          :placeholder="field.placeholder"
                        />
                        <label class="settings-toggle">
                          <input v-model="clearSecretFlags[field.key]" type="checkbox" class="settings-toggle__input" />
                          清空这个密钥
                        </label>
                      </div>
                    </div>
                  </section>
                </article>
              </template>
            </div>
          </div>

          <div class="settings-savebar">
            <button type="button" class="settings-primary-btn" :disabled="loading || saving" @click="handleSave">
              {{ saving ? '保存中...' : '保存配置' }}
            </button>
            <div class="flex min-w-0 flex-1 flex-wrap items-center gap-3">
              <span class="settings-status-chip settings-status-chip--neutral">
                {{ backendConfigLoaded ? '后端配置已加载' : '后端未连通，仅本地 API_URL 会生效' }}
              </span>
              <span v-if="probeMessage" class="text-sm font-medium" :class="probeStatus === 'success' ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'">
                {{ probeMessage }}
              </span>
            </div>
          </div>
        </section>

        <section class="settings-notes">
          <button type="button" class="settings-notes__toggle" @click="settingsNotesOpen = !settingsNotesOpen">
            <div>
              <p class="settings-section-eyebrow">Docs</p>
              <h3>配置说明</h3>
            </div>
            <span class="settings-notes__state">
              <span>{{ settingsNotesOpen ? '收起说明' : '展开说明' }}</span>
              <ChevronDown class="h-4 w-4 transition-transform" :class="{ 'rotate-180': settingsNotesOpen }" />
            </span>
          </button>

          <div v-if="settingsNotesOpen" class="settings-notes__body">
            <ul class="settings-note-list">
              <li v-for="note in settingsNotes" :key="note">{{ note }}</li>
            </ul>
          </div>
        </section>
      </section>
    </div>

    <Transition name="settings-dialog">
      <div v-if="guideDialogOpen" class="settings-guide-dialog-layer" @click.self="closeGuideDialog">
        <div class="settings-guide-dialog">
          <div class="settings-guide-dialog__head">
            <div>
              <div class="settings-guide-panel__badge">
                <Image class="h-3.5 w-3.5" />
                Guide Tutorial
              </div>
              <h3>{{ activeGuide.title }}</h3>
              <p>{{ activeGuide.summary }}</p>
            </div>
            <div class="settings-guide-dialog__head-actions">
              <span class="settings-inline-badge">
                步骤 {{ guideStepIndex[activePanel] + 1 }} / {{ activeGuide.steps.length }}
              </span>
              <button type="button" class="settings-guide-dialog__close" @click="closeGuideDialog">
                <X class="h-4 w-4" />
              </button>
            </div>
          </div>

          <div class="settings-guide-dialog__viewport-shell">
            <button type="button" class="settings-guide-dialog__nav" :disabled="!canPrevGuideStep" @click="prevGuideStep">
              <ChevronLeft class="h-4 w-4" />
            </button>

            <div class="settings-guide-dialog__viewport">
              <div class="settings-guide-dialog__track" :style="activeGuideTrackStyle">
                <article v-for="step in activeGuide.steps" :key="step.id" class="settings-guide-dialog__slide">
                  <button
                    type="button"
                    class="settings-guide-dialog__media"
                    @click="openGuideImage(step.image, step.alt, step.title)"
                  >
                    <img :src="step.image" :alt="step.alt" class="settings-guide-dialog__image" />
                    <span class="settings-guide-dialog__zoom">点击图片放大查看</span>
                  </button>
                  <div class="settings-guide-dialog__copy">
                    <p class="settings-section-eyebrow">{{ activeGuide.eyebrow }}</p>
                    <h4>{{ step.title }}</h4>
                    <p>{{ step.caption }}</p>
                    <div v-if="step.fields?.length" class="settings-guide-dialog__chips">
                      <span v-for="field in step.fields" :key="field" class="settings-status-chip settings-status-chip--neutral">
                        {{ field }}
                      </span>
                    </div>
                  </div>
                </article>
              </div>
            </div>

            <button type="button" class="settings-guide-dialog__nav" :disabled="!canNextGuideStep" @click="nextGuideStep">
              <ChevronRight class="h-4 w-4" />
            </button>
          </div>

          <div class="settings-guide-dialog__steps">
            <button
              v-for="(step, index) in activeGuide.steps"
              :key="step.id"
              type="button"
              class="settings-guide-dialog__step"
              :class="index === guideStepIndex[activePanel] ? 'settings-guide-dialog__step--active' : ''"
              @click="setGuideStep(activePanel, index)"
            >
              <span class="settings-guide-dialog__step-index">{{ index + 1 }}</span>
              <span class="settings-guide-dialog__step-copy">
                <strong>{{ step.title }}</strong>
                <span>{{ step.caption }}</span>
              </span>
            </button>
          </div>

          <div class="settings-guide-dialog__footer">
            <div v-if="activeGuide.secondaryCard" class="settings-guide-secondary settings-guide-dialog__secondary">
              <button
                v-if="activeGuide.secondaryCard.image"
                type="button"
                class="settings-guide-dialog__secondary-media"
                @click="openGuideImage(activeGuide.secondaryCard.image, activeGuide.secondaryCard.alt || activeGuide.secondaryCard.title, activeGuide.secondaryCard.title)"
              >
                <img
                  :src="activeGuide.secondaryCard.image"
                  :alt="activeGuide.secondaryCard.alt || activeGuide.secondaryCard.title"
                  class="settings-guide-secondary__image"
                />
                <span class="settings-guide-dialog__zoom">点击图片放大查看</span>
              </button>
              <div class="settings-guide-secondary__body">
                <p class="settings-section-eyebrow">补充参考</p>
                <h4>{{ activeGuide.secondaryCard.title }}</h4>
                <p>{{ activeGuide.secondaryCard.description }}</p>
                <div v-if="activeGuide.secondaryCard.fields?.length" class="settings-guide-dialog__chips">
                  <span v-for="field in activeGuide.secondaryCard.fields" :key="field" class="settings-status-chip settings-status-chip--neutral">
                    {{ field }}
                  </span>
                </div>
              </div>
            </div>

            <div class="settings-guide-panel__tips settings-guide-dialog__tips">
              <h4>填写提醒</h4>
              <ul class="settings-note-list settings-note-list--compact">
                <li v-for="tip in activeGuide.tips" :key="tip">{{ tip }}</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </Transition>

    <Transition name="settings-dialog">
      <div v-if="guideImageViewerOpen" class="settings-image-viewer-layer" @click.self="closeGuideImage">
        <div class="settings-image-viewer">
          <div class="settings-image-viewer__head">
            <div>
              <p class="settings-section-eyebrow">Image Preview</p>
              <h3>{{ guideViewerImage.title || '教程图片' }}</h3>
            </div>
            <button type="button" class="settings-guide-dialog__close" @click="closeGuideImage">
              <X class="h-4 w-4" />
            </button>
          </div>
          <div class="settings-image-viewer__body">
            <img :src="guideViewerImage.src" :alt="guideViewerImage.alt" class="settings-image-viewer__image" />
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
@reference "tailwindcss";

.settings-hero,
.settings-workbench,
.settings-dashboard-card,
.settings-runtime-hub {
  position: relative;
  border: 1px solid rgba(226, 232, 240, 0.86);
  background: #ffffff;
  box-shadow:
    0 20px 56px rgba(15, 23, 42, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.82);
}

.settings-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1.5rem;
  padding: 1.75rem;
  border-radius: 2rem;
  overflow: hidden;
}

.settings-hero::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(circle at 12% 18%, rgba(56, 189, 248, 0.14), transparent 28%),
    radial-gradient(circle at 82% 14%, rgba(139, 92, 246, 0.14), transparent 26%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.08), transparent 62%);
}

.settings-hero__copy {
  position: relative;
  z-index: 1;
  min-width: 0;
}

.settings-hero__badge,
.settings-hero__meta-chip,
.settings-inline-badge,
.settings-status-chip,
.settings-stage__badge {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  border-radius: 9999px;
  font-size: 0.74rem;
  font-weight: 700;
}

.settings-hero__badge {
  padding: 0.4rem 0.8rem;
  border: 1px solid rgba(226, 232, 240, 0.88);
  background: rgba(255, 255, 255, 0.8);
  color: #475569;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.settings-hero h1 {
  margin-top: 1rem;
  font-size: clamp(2rem, 3vw, 3rem);
  font-weight: 800;
  line-height: 1.05;
  letter-spacing: -0.04em;
  color: #0f172a;
}

.settings-hero p {
  margin-top: 0.9rem;
  max-width: 56rem;
  font-size: 0.95rem;
  line-height: 1.8;
  color: #475569;
}

.settings-hero__meta {
  position: relative;
  z-index: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-top: 1.4rem;
}

.settings-hero__meta-chip {
  padding: 0.55rem 0.85rem;
  border: 1px solid rgba(226, 232, 240, 0.88);
  background: rgba(255, 255, 255, 0.72);
  color: #334155;
}

.settings-workbench,
.settings-dashboard-card,
.settings-runtime-hub {
  border-radius: 2rem;
  padding: 1.5rem;
}

.settings-workbench__top,
.settings-dashboard-card__head,
.settings-stage__intro {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.settings-workbench__top h2,
.settings-dashboard-card__head h2,
.settings-dashboard-card__head h3,
.settings-stage__title {
  color: #0f172a;
}

.settings-workbench__top h2 {
  font-size: 1.25rem;
  font-weight: 800;
}

.settings-workbench__top p,
.settings-dashboard-card__head p,
.settings-stage__desc,
.settings-form-card__desc,
.settings-helper {
  color: #64748b;
}

.settings-workbench__top p,
.settings-dashboard-card__head p,
.settings-stage__desc {
  margin-top: 0.4rem;
  font-size: 0.9rem;
  line-height: 1.65;
}

.settings-section-eyebrow,
.settings-stage__eyebrow,
.settings-form-card__eyebrow,
.settings-panel-button__eyebrow {
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: #94a3b8;
}

.settings-ghost-btn,
.settings-secondary-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.55rem;
  border-radius: 1rem;
  border: 1px solid rgba(226, 232, 240, 0.92);
  background: rgba(255, 255, 255, 0.84);
  color: #475569;
  font-size: 0.86rem;
  font-weight: 700;
  transition:
    transform 180ms ease,
    border-color 180ms ease,
    background-color 180ms ease,
    color 180ms ease;
}

.settings-ghost-btn {
  padding: 0.85rem 1rem;
}

.settings-secondary-btn {
  padding: 0.7rem 0.9rem;
}

.settings-ghost-btn:hover:not(:disabled),
.settings-secondary-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  border-color: rgba(129, 140, 248, 0.42);
  background: rgba(238, 242, 255, 0.86);
  color: #4338ca;
}

.settings-alert {
  margin-top: 1.25rem;
  border-radius: 1.25rem;
  padding: 0.95rem 1rem;
  font-size: 0.9rem;
  font-weight: 600;
}

.settings-alert--error {
  border: 1px solid rgba(248, 113, 113, 0.28);
  background: rgba(254, 242, 242, 0.9);
  color: #b91c1c;
}

.settings-alert--success {
  border: 1px solid rgba(16, 185, 129, 0.24);
  background: rgba(236, 253, 245, 0.9);
  color: #047857;
}

.settings-panel-stage {
  margin-top: 1.5rem;
  border-radius: 1.7rem;
  border: 1px solid rgba(226, 232, 240, 0.86);
  background: rgba(248, 250, 252, 0.7);
  padding: 1rem;
}

.settings-panel-stage__intro {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
}

.settings-panel-stage__intro h3 {
  margin-top: 0.45rem;
  font-size: 1.15rem;
  font-weight: 800;
  color: #0f172a;
}

.settings-panel-stage__intro p {
  margin-top: 0.45rem;
  max-width: 42rem;
  font-size: 0.88rem;
  line-height: 1.7;
  color: #64748b;
}

.settings-step-nav {
  display: grid;
  gap: 0.9rem;
  margin-top: 1.2rem;
}

.settings-step-nav__item {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 0.9rem;
  align-items: start;
  border-radius: 1.3rem;
  border: 1px solid rgba(226, 232, 240, 0.9);
  background: rgba(255, 255, 255, 0.82);
  padding: 1rem;
  text-align: left;
  transition:
    transform 180ms ease,
    border-color 180ms ease,
    box-shadow 180ms ease,
    background-color 180ms ease;
}

.settings-step-nav__item:hover {
  transform: translateY(-1px);
  border-color: rgba(129, 140, 248, 0.3);
  box-shadow: 0 12px 24px rgba(15, 23, 42, 0.06);
}

.settings-step-nav__item--active {
  border-color: rgba(129, 140, 248, 0.34);
  background: rgba(248, 250, 255, 0.96);
  box-shadow: 0 0 0 2px rgba(129, 140, 248, 0.12);
}

.settings-step-nav__lead {
  display: inline-flex;
  align-items: center;
  gap: 0.6rem;
}

.settings-step-nav__index,
.settings-step-nav__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border-radius: 9999px;
  border: 1px solid rgba(226, 232, 240, 0.9);
  background: rgba(255, 255, 255, 0.94);
  color: #475569;
  font-size: 0.78rem;
  font-weight: 800;
}

.settings-step-nav__item--active .settings-step-nav__index,
.settings-step-nav__item--active .settings-step-nav__icon {
  border-color: rgba(199, 210, 254, 0.92);
  background: rgba(238, 242, 255, 0.94);
  color: #4338ca;
}

.settings-step-nav__copy {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 0.22rem;
}

.settings-step-nav__copy strong {
  font-size: 0.92rem;
  font-weight: 800;
  color: #0f172a;
}

.settings-step-nav__copy span {
  font-size: 0.79rem;
  line-height: 1.62;
  color: #64748b;
}

.settings-step-nav__state {
  grid-column: 2;
  display: inline-flex;
  width: fit-content;
  margin-top: 0.15rem;
  border-radius: 9999px;
  border: 1px solid rgba(226, 232, 240, 0.88);
  background: rgba(255, 255, 255, 0.9);
  padding: 0.42rem 0.72rem;
  font-size: 0.74rem;
  font-weight: 700;
  color: #475569;
}

.settings-panel-stage__intro,
.settings-stage-card,
.settings-stage,
.settings-panel-button {
  display: none;
}

.settings-stage-card {
  position: relative;
  display: flex;
  min-height: calc(206px - 2rem);
  flex-direction: column;
}

.settings-stage-card__top {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.settings-stage-card__eyebrow {
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: #94a3b8;
}

.settings-stage-card__badge,
.settings-stage-card__indicator {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 700;
}

.settings-stage-card__badge {
  background: rgba(226, 232, 240, 0.72);
  padding: 0.35rem 0.72rem;
  color: #64748b;
}

.settings-stage-card__badge--active {
  background: rgba(224, 231, 255, 0.88);
  color: #4338ca;
}

.settings-stage-card__title {
  position: relative;
  z-index: 1;
  margin-top: 0.9rem;
  font-size: 1.08rem;
  font-weight: 800;
  color: #0f172a;
}

.settings-stage-card__desc {
  position: relative;
  z-index: 1;
  margin-top: 0.45rem;
  font-size: 0.84rem;
  line-height: 1.65;
  color: #64748b;
}

.settings-stage-card__indicator {
  position: relative;
  z-index: 1;
  margin-top: auto;
  padding: 0.42rem 0.8rem;
  background: rgba(255, 255, 255, 0.86);
  color: #334155;
}

.settings-stage-card--identity::after,
.settings-stage-card--models::after,
.settings-stage-card--capabilities::after {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.6;
}

.settings-stage-card--identity::after {
  background: linear-gradient(135deg, rgba(14, 165, 233, 0.12), transparent 68%);
}

.settings-stage-card--models::after {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.14), transparent 68%);
}

.settings-stage-card--capabilities::after {
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.12), transparent 68%);
}

.settings-panel-grid {
  display: grid;
  gap: 0.9rem;
  margin-top: 1.5rem;
}

.settings-panel-button {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.55rem;
  min-height: 176px;
  padding: 1.15rem;
  overflow: hidden;
  border-radius: 1.6rem;
  border: 1px solid rgba(226, 232, 240, 0.92);
  background: rgba(255, 255, 255, 0.72);
  text-align: left;
  transition:
    transform 180ms ease,
    border-color 180ms ease,
    box-shadow 180ms ease,
    background-color 180ms ease;
}

.settings-panel-button::before {
  content: '';
  position: absolute;
  inset: 0;
  opacity: 0;
  transition: opacity 180ms ease;
}

.settings-panel-button--identity::before {
  background: linear-gradient(135deg, rgba(14, 165, 233, 0.14), transparent 68%);
}

.settings-panel-button--models::before {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.16), transparent 68%);
}

.settings-panel-button--capabilities::before {
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.14), transparent 68%);
}

.settings-panel-button:hover,
.settings-panel-button--active {
  transform: translateY(-2px);
  border-color: rgba(129, 140, 248, 0.34);
  box-shadow: 0 18px 36px rgba(79, 70, 229, 0.1);
}

.settings-panel-button:hover::before,
.settings-panel-button--active::before {
  opacity: 1;
}

.settings-panel-button__title {
  position: relative;
  z-index: 1;
  font-size: 1.05rem;
  font-weight: 800;
  color: #0f172a;
}

.settings-panel-button__desc,
.settings-panel-button__indicator {
  position: relative;
  z-index: 1;
}

.settings-panel-button__desc {
  font-size: 0.86rem;
  line-height: 1.65;
  color: #64748b;
}

.settings-panel-button__indicator {
  margin-top: auto;
  display: inline-flex;
  align-items: center;
  min-height: 2rem;
  border-radius: 9999px;
  background: rgba(255, 255, 255, 0.84);
  padding: 0.45rem 0.8rem;
  font-size: 0.78rem;
  font-weight: 700;
  color: #334155;
}

.settings-stage {
  margin-top: 1.5rem;
  border-radius: 1.8rem;
  border: 1px solid rgba(226, 232, 240, 0.86);
  background: rgba(248, 250, 252, 0.72);
  padding: 1.2rem;
}

.settings-editor-card {
  margin-top: 1.5rem;
  border-radius: 1.8rem;
  border: 1px solid rgba(226, 232, 240, 0.86);
  background: #ffffff;
  padding: 1.2rem;
  box-shadow:
    0 18px 48px rgba(15, 23, 42, 0.05),
    inset 0 1px 0 rgba(255, 255, 255, 0.84);
}

.settings-editor-card__head,
.settings-runtime-board__head,
.settings-runtime-hub__head,
.settings-guide-panel__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.settings-editor-card__head h3,
.settings-runtime-board__head h3,
.settings-runtime-hub__head h3,
.settings-guide-panel__head h3,
.settings-dashboard-card__head h4,
.settings-guide-panel__preview-copy h4,
.settings-guide-secondary__body h4,
.settings-notes__toggle h3 {
  color: #0f172a;
}

.settings-editor-card__head h3,
.settings-runtime-board__head h3,
.settings-runtime-hub__head h3 {
  margin-top: 0.45rem;
  font-size: 1.15rem;
  font-weight: 800;
}

.settings-dashboard-card__head h4 {
  margin-top: 0.4rem;
  font-size: 1rem;
  font-weight: 800;
}

.settings-editor-card__head p,
.settings-runtime-board__head p,
.settings-runtime-hub__head p,
.settings-guide-panel__head p,
.settings-guide-panel__preview-copy p,
.settings-guide-secondary__body p {
  color: #64748b;
}

.settings-editor-card__head p,
.settings-runtime-board__head p,
.settings-runtime-hub__head p,
.settings-guide-panel__head p {
  margin-top: 0.45rem;
  max-width: 42rem;
  font-size: 0.88rem;
  line-height: 1.7;
}

.settings-editor-card__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 0.75rem;
}

.settings-editor-card__body {
  margin-top: 1.15rem;
  border-radius: 1.5rem;
  border: 1px solid rgba(226, 232, 240, 0.82);
  background: #ffffff;
  padding: 1rem;
}

.settings-editor-card__form {
  min-width: 0;
}

.settings-config-card {
  display: grid;
  gap: 1rem;
}

.settings-config-card__summary {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.8rem;
  padding: 0.1rem 0.1rem 0.3rem;
}

.settings-config-card__note {
  max-width: 46rem;
  font-size: 0.88rem;
  line-height: 1.7;
  color: #64748b;
}

.settings-config-card__grid {
  display: grid;
  gap: 1rem;
}

.settings-config-card__grid--two {
  grid-template-columns: 1fr;
}

.settings-config-card__block {
  border-radius: 1.55rem;
  border: 1px solid rgba(226, 232, 240, 0.88);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(248, 250, 252, 0.9) 100%);
  padding: 1.15rem;
  box-shadow:
    0 14px 32px rgba(15, 23, 42, 0.04),
    inset 0 1px 0 rgba(255, 255, 255, 0.72);
}

.settings-guide-panel {
  display: flex;
  height: 100%;
  flex-direction: column;
  gap: 1rem;
  border-radius: 1.5rem;
  border: 1px solid rgba(226, 232, 240, 0.86);
  background: rgba(255, 255, 255, 0.9);
  padding: 1rem;
}

.settings-guide-panel__badge {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  border-radius: 9999px;
  border: 1px solid rgba(226, 232, 240, 0.88);
  background: rgba(255, 255, 255, 0.84);
  padding: 0.42rem 0.8rem;
  font-size: 0.74rem;
  font-weight: 700;
  color: #475569;
}

.settings-guide-panel__preview {
  overflow: hidden;
  border-radius: 1.3rem;
  border: 1px solid rgba(226, 232, 240, 0.86);
  background: rgba(248, 250, 252, 0.82);
}

.settings-guide-panel__image,
.settings-guide-secondary__image {
  display: block;
  width: 100%;
  max-height: 320px;
  object-fit: contain;
  object-position: center top;
  background: #ffffff;
}

.settings-guide-panel__preview-copy {
  padding: 0.95rem 1rem 1rem;
}

.settings-guide-panel__preview-copy h4,
.settings-guide-secondary__body h4 {
  margin-top: 0.45rem;
  font-size: 1rem;
  font-weight: 800;
}

.settings-guide-panel__preview-copy p,
.settings-guide-secondary__body p {
  margin-top: 0.35rem;
  font-size: 0.83rem;
  line-height: 1.65;
}

.settings-guide-panel__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.settings-guide-panel__steps {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.settings-guide-step {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  border-radius: 1rem;
  border: 1px solid rgba(226, 232, 240, 0.86);
  background: rgba(255, 255, 255, 0.84);
  padding: 0.85rem 0.9rem;
  text-align: left;
  transition:
    transform 180ms ease,
    border-color 180ms ease,
    box-shadow 180ms ease,
    background-color 180ms ease;
}

.settings-guide-step:hover {
  transform: translateY(-1px);
  border-color: rgba(129, 140, 248, 0.28);
  box-shadow: 0 12px 24px rgba(15, 23, 42, 0.06);
}

.settings-guide-step--active {
  border-color: rgba(129, 140, 248, 0.34);
  background: rgba(238, 242, 255, 0.82);
  box-shadow: 0 0 0 2px rgba(129, 140, 248, 0.12);
}

.settings-guide-step__index {
  display: inline-flex;
  width: 1.9rem;
  height: 1.9rem;
  flex: none;
  align-items: center;
  justify-content: center;
  border-radius: 9999px;
  border: 1px solid rgba(226, 232, 240, 0.88);
  background: rgba(248, 250, 252, 0.96);
  font-size: 0.78rem;
  font-weight: 800;
  color: #475569;
}

.settings-guide-step__copy {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 0.2rem;
}

.settings-guide-step__copy strong {
  font-size: 0.88rem;
  font-weight: 800;
  color: #0f172a;
}

.settings-guide-step__copy span {
  font-size: 0.78rem;
  line-height: 1.6;
  color: #64748b;
}

.settings-guide-secondary {
  display: grid;
  gap: 0.9rem;
  border-radius: 1.25rem;
  border: 1px solid rgba(226, 232, 240, 0.86);
  background: rgba(248, 250, 252, 0.84);
  padding: 0.9rem;
}

.settings-guide-secondary__media {
  overflow: hidden;
  border-radius: 1rem;
  border: 1px solid rgba(226, 232, 240, 0.82);
  background: rgba(255, 255, 255, 0.92);
}

.settings-guide-panel__tips {
  padding-top: 0.95rem;
  border-top: 1px solid rgba(226, 232, 240, 0.82);
}

.settings-guide-panel__tips h4 {
  font-size: 0.92rem;
  font-weight: 800;
  color: #0f172a;
}

.settings-note-list--compact {
  gap: 0.55rem;
  margin-top: 0.7rem;
  font-size: 0.82rem;
}

.settings-note-list--compact li {
  padding-left: 0.9rem;
}

.settings-note-list--compact li::before {
  top: 0.58rem;
}

.settings-runtime-hub {
  margin-top: 1.5rem;
}

.settings-runtime-hub__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 0.75rem;
}

.settings-runtime-hub__grid {
  display: grid;
  gap: 1rem;
  margin-top: 1rem;
}

.settings-runtime-hub__section {
  height: 100%;
  border-radius: 1.5rem;
  border: 1px solid rgba(226, 232, 240, 0.84);
  background: #ffffff;
  padding: 1.1rem;
  box-shadow:
    0 16px 36px rgba(15, 23, 42, 0.04),
    inset 0 1px 0 rgba(255, 255, 255, 0.74);
}

.settings-runtime-hub__section--overview {
  position: relative;
  overflow: hidden;
}

.settings-runtime-hub__section--overview::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(circle at 14% 18%, rgba(56, 189, 248, 0.1), transparent 28%),
    radial-gradient(circle at 86% 12%, rgba(34, 197, 94, 0.08), transparent 24%);
}

.settings-runtime-hub__section--overview > * {
  position: relative;
  z-index: 1;
}

.settings-metric-grid--overview {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.settings-metric--overview {
  min-height: 116px;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  padding: 1rem 1.05rem;
}

.settings-runtime-status {
  display: grid;
  gap: 0.9rem;
  margin-top: 1rem;
}

.settings-runtime-status__summary {
  display: grid;
  gap: 0.75rem;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.settings-runtime-status__tile,
.settings-runtime-status__models {
  border-radius: 1.2rem;
  border: 1px solid rgba(226, 232, 240, 0.86);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(248, 250, 252, 0.92) 100%);
  box-shadow:
    0 12px 28px rgba(15, 23, 42, 0.04),
    inset 0 1px 0 rgba(255, 255, 255, 0.74);
}

.settings-runtime-status__tile {
  padding: 0.9rem 0.95rem;
}

.settings-runtime-status__tile:last-child {
  grid-column: 1 / -1;
}

.settings-runtime-status__models {
  display: grid;
  gap: 0.8rem;
  padding: 0.95rem;
}

.settings-runtime-status__models-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.settings-runtime-status__model-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.85rem;
  border-radius: 1rem;
  border: 1px solid rgba(226, 232, 240, 0.82);
  background: #ffffff;
  padding: 0.8rem 0.85rem;
}

.settings-guide-dialog-layer,
.settings-image-viewer-layer {
  position: fixed;
  inset: 0;
  z-index: 70;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.5rem;
  background: rgba(15, 23, 42, 0.18);
}

.settings-guide-dialog,
.settings-image-viewer {
  width: min(1120px, 100%);
  max-height: calc(100vh - 3rem);
  overflow: auto;
  border-radius: 1.8rem;
  border: 1px solid rgba(226, 232, 240, 0.9);
  background: #ffffff;
  box-shadow: 0 28px 80px rgba(15, 23, 42, 0.18);
}

.settings-guide-dialog {
  padding: 1.3rem;
}

.settings-image-viewer {
  width: min(1200px, 100%);
  padding: 1.2rem;
}

.settings-guide-dialog__head,
.settings-image-viewer__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.settings-guide-dialog__head h3,
.settings-image-viewer__head h3 {
  margin-top: 0.5rem;
  font-size: 1.25rem;
  font-weight: 800;
  color: #0f172a;
}

.settings-guide-dialog__head p {
  margin-top: 0.45rem;
  max-width: 44rem;
  font-size: 0.88rem;
  line-height: 1.7;
  color: #64748b;
}

.settings-guide-dialog__head-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.settings-guide-dialog__close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 9999px;
  border: 1px solid rgba(226, 232, 240, 0.88);
  background: rgba(255, 255, 255, 0.92);
  color: #64748b;
  transition:
    transform 180ms ease,
    border-color 180ms ease,
    color 180ms ease;
}

.settings-guide-dialog__close:hover {
  transform: translateY(-1px);
  border-color: rgba(129, 140, 248, 0.32);
  color: #4338ca;
}

.settings-guide-dialog__viewport-shell {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 0.9rem;
  align-items: center;
  margin-top: 1.2rem;
}

.settings-guide-dialog__nav {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.75rem;
  height: 2.75rem;
  border-radius: 9999px;
  border: 1px solid rgba(226, 232, 240, 0.9);
  background: rgba(255, 255, 255, 0.94);
  color: #475569;
  transition:
    transform 180ms ease,
    border-color 180ms ease,
    color 180ms ease,
    box-shadow 180ms ease;
}

.settings-guide-dialog__nav:hover:not(:disabled) {
  transform: translateY(-1px);
  border-color: rgba(129, 140, 248, 0.32);
  color: #4338ca;
  box-shadow: 0 12px 24px rgba(15, 23, 42, 0.08);
}

.settings-guide-dialog__nav:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.settings-guide-dialog__viewport {
  overflow: hidden;
  border-radius: 1.5rem;
  border: 1px solid rgba(226, 232, 240, 0.86);
  background: rgba(248, 250, 252, 0.76);
}

.settings-guide-dialog__track {
  display: flex;
  transition: transform 280ms cubic-bezier(0.4, 0, 0.2, 1);
  will-change: transform;
}

.settings-guide-dialog__slide {
  display: grid;
  width: 100%;
  min-width: 100%;
  gap: 1rem;
  padding: 1rem;
}

.settings-guide-dialog__media,
.settings-guide-dialog__secondary-media {
  position: relative;
  overflow: hidden;
  border-radius: 1.3rem;
  border: 1px solid rgba(226, 232, 240, 0.88);
  background: rgba(255, 255, 255, 0.94);
}

.settings-guide-dialog__image {
  display: block;
  width: 100%;
  max-height: 440px;
  object-fit: contain;
  background: #ffffff;
}

.settings-guide-dialog__zoom {
  position: absolute;
  right: 0.85rem;
  bottom: 0.85rem;
  border-radius: 9999px;
  background: rgba(15, 23, 42, 0.72);
  padding: 0.42rem 0.72rem;
  font-size: 0.74rem;
  font-weight: 700;
  color: #ffffff;
}

.settings-guide-dialog__copy h4 {
  margin-top: 0.5rem;
  font-size: 1.02rem;
  font-weight: 800;
  color: #0f172a;
}

.settings-guide-dialog__copy p {
  margin-top: 0.4rem;
  font-size: 0.86rem;
  line-height: 1.72;
  color: #64748b;
}

.settings-guide-dialog__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.9rem;
}

.settings-guide-dialog__steps {
  display: grid;
  gap: 0.75rem;
  margin-top: 1.1rem;
}

.settings-guide-dialog__step {
  display: flex;
  align-items: flex-start;
  gap: 0.8rem;
  border-radius: 1.1rem;
  border: 1px solid rgba(226, 232, 240, 0.88);
  background: rgba(248, 250, 252, 0.82);
  padding: 0.9rem;
  text-align: left;
  transition:
    transform 180ms ease,
    border-color 180ms ease,
    box-shadow 180ms ease;
}

.settings-guide-dialog__step:hover {
  transform: translateY(-1px);
  border-color: rgba(129, 140, 248, 0.3);
  box-shadow: 0 10px 22px rgba(15, 23, 42, 0.06);
}

.settings-guide-dialog__step--active {
  border-color: rgba(129, 140, 248, 0.34);
  background: rgba(238, 242, 255, 0.86);
  box-shadow: 0 0 0 2px rgba(129, 140, 248, 0.12);
}

.settings-guide-dialog__step-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  flex: none;
  border-radius: 9999px;
  border: 1px solid rgba(226, 232, 240, 0.88);
  background: rgba(255, 255, 255, 0.94);
  font-size: 0.8rem;
  font-weight: 800;
  color: #475569;
}

.settings-guide-dialog__step-copy {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 0.2rem;
}

.settings-guide-dialog__step-copy strong {
  font-size: 0.88rem;
  font-weight: 800;
  color: #0f172a;
}

.settings-guide-dialog__step-copy span {
  font-size: 0.78rem;
  line-height: 1.62;
  color: #64748b;
}

.settings-guide-dialog__footer {
  display: grid;
  gap: 1rem;
  margin-top: 1.1rem;
}

.settings-guide-dialog__secondary,
.settings-guide-dialog__tips {
  margin-top: 0;
}

.settings-guide-dialog__secondary-media {
  display: block;
}

.settings-image-viewer__body {
  margin-top: 1rem;
  overflow: auto;
  border-radius: 1.4rem;
  border: 1px solid rgba(226, 232, 240, 0.88);
  background: rgba(248, 250, 252, 0.78);
  padding: 0.9rem;
}

.settings-image-viewer__image {
  display: block;
  width: 100%;
  max-height: calc(100vh - 10rem);
  object-fit: contain;
  background: #ffffff;
}

.settings-dialog-enter-active,
.settings-dialog-leave-active {
  transition: opacity 180ms ease, transform 180ms ease;
}

.settings-dialog-enter-from,
.settings-dialog-leave-to {
  opacity: 0;
}

.settings-notes {
  margin-top: 1.5rem;
  overflow: hidden;
  border-radius: 1.6rem;
  border: 1px solid rgba(226, 232, 240, 0.86);
  background: rgba(248, 250, 252, 0.72);
}

.settings-notes__toggle {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 1.1rem 1.2rem;
  text-align: left;
}

.settings-notes__state {
  display: inline-flex;
  align-items: center;
  gap: 0.6rem;
  font-size: 0.84rem;
  font-weight: 700;
  color: #475569;
}

.settings-notes__body {
  padding: 0 1.2rem 1.15rem;
  border-top: 1px solid rgba(226, 232, 240, 0.82);
}

.settings-stage__badge,
.settings-inline-badge,
.settings-status-chip--neutral {
  padding: 0.5rem 0.85rem;
  background: rgba(255, 255, 255, 0.82);
  color: #475569;
}

.settings-inline-badge {
  border: 1px solid rgba(226, 232, 240, 0.86);
}

.settings-field-grid {
  display: grid;
  gap: 1rem;
  margin-top: 1.1rem;
}

.settings-form-card {
  border-radius: 1.5rem;
  border: 1px solid rgba(226, 232, 240, 0.86);
  background: rgba(255, 255, 255, 0.88);
  padding: 1.1rem;
}

.settings-form-card__head {
  display: flex;
  align-items: flex-start;
  gap: 0.85rem;
  margin-bottom: 1rem;
}

.settings-form-card__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.4rem;
  height: 2.4rem;
  flex-shrink: 0;
  border-radius: 1rem;
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.14), rgba(99, 102, 241, 0.14));
  color: #4338ca;
}

.settings-form-card__title {
  font-size: 1rem;
  font-weight: 800;
}

.settings-form-card__desc {
  margin-top: 0.3rem;
  font-size: 0.82rem;
  line-height: 1.6;
}

.settings-label {
  display: block;
  font-size: 0.88rem;
  font-weight: 700;
  color: #1f2937;
}

.settings-helper {
  margin-top: 0.35rem;
  font-size: 0.78rem;
  line-height: 1.6;
}

.settings-input {
  width: 100%;
  margin-top: 0.75rem;
  padding: 0.9rem 1rem;
  border-radius: 1rem;
  border: 1px solid rgba(203, 213, 225, 0.92);
  background: rgba(255, 255, 255, 0.94);
  color: #0f172a;
  outline: none;
  transition:
    border-color 180ms ease,
    box-shadow 180ms ease,
    background-color 180ms ease;
}

.settings-input::placeholder {
  color: #94a3b8;
}

.settings-input:focus {
  border-color: rgba(99, 102, 241, 0.46);
  box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.12);
}

.settings-sensitive-stack,
.settings-sensitive-item {
  display: flex;
  flex-direction: column;
  gap: 0.7rem;
}

.settings-sensitive-item + .settings-sensitive-item {
  padding-top: 0.9rem;
  border-top: 1px solid rgba(226, 232, 240, 0.76);
}

.settings-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.55rem;
  font-size: 0.78rem;
  font-weight: 600;
  color: #64748b;
}

.settings-toggle__input {
  width: 1rem;
  height: 1rem;
  accent-color: #4f46e5;
}

.settings-status-chip {
  width: fit-content;
}

.settings-status-chip--success {
  padding: 0.45rem 0.8rem;
  background: rgba(220, 252, 231, 0.92);
  color: #047857;
}

.settings-status-chip--warning {
  padding: 0.45rem 0.8rem;
  background: rgba(254, 249, 195, 0.92);
  color: #a16207;
}

.settings-savebar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 1rem;
  margin-top: 1.5rem;
  padding-top: 1.25rem;
  border-top: 1px solid rgba(226, 232, 240, 0.82);
}

.settings-primary-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 138px;
  padding: 0.95rem 1.2rem;
  border: 0;
  border-radius: 1rem;
  background: linear-gradient(90deg, #2563eb 0%, #4f46e5 50%, #db2777 100%);
  color: white;
  font-size: 0.9rem;
  font-weight: 800;
  transition:
    transform 180ms ease,
    box-shadow 180ms ease,
    opacity 180ms ease;
  box-shadow: 0 18px 36px rgba(79, 70, 229, 0.18);
}

.settings-primary-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 22px 40px rgba(79, 70, 229, 0.22);
}

.settings-primary-btn:disabled,
.settings-ghost-btn:disabled,
.settings-secondary-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.settings-dashboard-card--lead {
  overflow: hidden;
}

.settings-dashboard-card--lead::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(circle at 14% 18%, rgba(56, 189, 248, 0.14), transparent 28%),
    radial-gradient(circle at 86% 12%, rgba(34, 197, 94, 0.14), transparent 24%);
}

.settings-metric-grid {
  position: relative;
  z-index: 1;
  display: grid;
  gap: 0.85rem;
  margin-top: 1.2rem;
}

.settings-metric,
.settings-dashboard-list__item,
.settings-model-row,
.settings-model-empty {
  border-radius: 1.25rem;
  border: 1px solid rgba(226, 232, 240, 0.84);
  background: rgba(255, 255, 255, 0.84);
}

.settings-metric {
  padding: 0.95rem 1rem;
}

.settings-metric__label {
  display: block;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #94a3b8;
}

.settings-metric__value {
  display: block;
  margin-top: 0.45rem;
  font-size: 0.96rem;
  line-height: 1.55;
  color: #0f172a;
}

.settings-model-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.8rem;
  padding: 0.95rem 1rem;
}

.settings-model-empty {
  padding: 1rem;
  font-size: 0.86rem;
  color: #64748b;
}

.settings-dashboard-list {
  display: flex;
  flex-direction: column;
  gap: 0.8rem;
  margin-top: 1rem;
}

.settings-dashboard-list__item {
  padding: 0.95rem 1rem;
}

.settings-note-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-top: 1rem;
  color: #475569;
  font-size: 0.88rem;
  line-height: 1.7;
}

.settings-note-list li {
  list-style: none;
  padding-left: 1rem;
  position: relative;
}

.settings-note-list li::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0.68rem;
  width: 0.38rem;
  height: 0.38rem;
  border-radius: 9999px;
  background: linear-gradient(135deg, #38bdf8, #818cf8);
}

@media (min-width: 768px) {
  .settings-panel-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .settings-step-nav {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .settings-field-grid--two {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .settings-guide-dialog__steps {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .settings-config-card__grid--two,
  .settings-metric-grid--overview {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (min-width: 1120px) {
  .settings-step-nav {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .settings-guide-dialog__slide {
    grid-template-columns: minmax(0, 1.24fr) minmax(320px, 0.92fr);
    align-items: start;
  }

  .settings-guide-dialog__footer {
    grid-template-columns: minmax(0, 1.02fr) minmax(320px, 0.98fr);
    align-items: start;
  }

  .settings-runtime-hub__grid {
    grid-template-columns: minmax(0, 1.16fr) minmax(320px, 0.82fr);
  }
}

@media (max-width: 767px) {
  .settings-hero,
  .settings-workbench__top,
  .settings-editor-card__head,
  .settings-editor-card__actions,
  .settings-guide-panel__head,
  .settings-guide-dialog__head,
  .settings-image-viewer__head,
  .settings-runtime-hub__head,
  .settings-dashboard-card__head,
  .settings-stage__intro,
  .settings-notes__toggle {
    flex-direction: column;
  }

  .settings-hero {
    padding: 1.25rem;
  }

  .settings-workbench,
  .settings-dashboard-card {
    padding: 1.15rem;
  }

  .settings-editor-card,
  .settings-runtime-hub,
  .settings-guide-dialog,
  .settings-image-viewer {
    padding: 1.15rem;
  }

  .settings-guide-dialog-layer,
  .settings-image-viewer-layer {
    padding: 0.9rem;
  }

  .settings-guide-dialog__viewport-shell {
    grid-template-columns: 1fr;
  }

  .settings-guide-dialog__nav {
    display: none;
  }

  .settings-metric-grid--overview,
  .settings-runtime-status__summary {
    grid-template-columns: 1fr;
  }
}

:global(html.dark) .settings-hero,
:global(html.dark) .settings-workbench,
:global(html.dark) .settings-dashboard-card,
:global(html.dark) .settings-runtime-hub,
:global(html.dark) .settings-editor-card,
:global(html.dark) .settings-guide-dialog,
:global(html.dark) .settings-image-viewer,
:global(html.dark) .settings-notes {
  border-color: rgba(255, 255, 255, 0.08);
  background:
    linear-gradient(180deg, rgba(10, 12, 20, 0.92) 0%, rgba(9, 11, 19, 0.96) 100%);
  box-shadow:
    0 24px 80px rgba(0, 0, 0, 0.34),
    inset 0 1px 0 rgba(255, 255, 255, 0.03);
}

:global(html.dark) .settings-hero__badge,
:global(html.dark) .settings-hero__meta-chip,
:global(html.dark) .settings-inline-badge,
:global(html.dark) .settings-guide-panel__badge,
:global(html.dark) .settings-stage__badge,
:global(html.dark) .settings-step-nav__item,
:global(html.dark) .settings-step-nav__index,
:global(html.dark) .settings-step-nav__icon,
:global(html.dark) .settings-step-nav__state,
:global(html.dark) .settings-status-chip--neutral,
:global(html.dark) .settings-metric,
:global(html.dark) .settings-dashboard-list__item,
:global(html.dark) .settings-model-row,
:global(html.dark) .settings-model-empty,
:global(html.dark) .settings-config-card__block,
:global(html.dark) .settings-runtime-status__tile,
:global(html.dark) .settings-runtime-status__models,
:global(html.dark) .settings-runtime-status__model-row,
:global(html.dark) .settings-runtime-hub__section,
:global(html.dark) .settings-editor-card__body,
:global(html.dark) .settings-guide-panel,
:global(html.dark) .settings-guide-step,
:global(html.dark) .settings-guide-dialog__media,
:global(html.dark) .settings-guide-dialog__nav,
:global(html.dark) .settings-guide-dialog__close,
:global(html.dark) .settings-guide-dialog__viewport,
:global(html.dark) .settings-guide-dialog__step,
:global(html.dark) .settings-guide-dialog__step-index,
:global(html.dark) .settings-guide-secondary,
:global(html.dark) .settings-guide-dialog__secondary-media,
:global(html.dark) .settings-image-viewer__body,
:global(html.dark) .settings-form-card,
:global(html.dark) .settings-ghost-btn,
:global(html.dark) .settings-secondary-btn {
  border-color: rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
  color: #cbd5e1;
}

:global(html.dark) .settings-hero h1,
:global(html.dark) .settings-workbench__top h2,
:global(html.dark) .settings-dashboard-card__head h2,
:global(html.dark) .settings-dashboard-card__head h3,
:global(html.dark) .settings-dashboard-card__head h4,
:global(html.dark) .settings-editor-card__head h3,
:global(html.dark) .settings-guide-panel__head h3,
:global(html.dark) .settings-guide-dialog__head h3,
:global(html.dark) .settings-image-viewer__head h3,
:global(html.dark) .settings-guide-panel__preview-copy h4,
:global(html.dark) .settings-guide-dialog__copy h4,
:global(html.dark) .settings-guide-secondary__body h4,
:global(html.dark) .settings-step-nav__copy strong,
:global(html.dark) .settings-guide-panel__tips h4,
:global(html.dark) .settings-runtime-hub__head h3,
:global(html.dark) .settings-runtime-board__head h3,
:global(html.dark) .settings-notes__toggle h3,
:global(html.dark) .settings-stage__title,
:global(html.dark) .settings-form-card__title,
:global(html.dark) .settings-label,
:global(html.dark) .settings-metric__value,
:global(html.dark) .settings-config-card__note strong,
:global(html.dark) .settings-runtime-status__model-row .font-semibold {
  color: rgba(255, 255, 255, 0.96);
}

:global(html.dark) .settings-hero p,
:global(html.dark) .settings-workbench__top p,
:global(html.dark) .settings-dashboard-card__head p,
:global(html.dark) .settings-editor-card__head p,
:global(html.dark) .settings-guide-panel__head p,
:global(html.dark) .settings-guide-dialog__head p,
:global(html.dark) .settings-guide-panel__preview-copy p,
:global(html.dark) .settings-guide-dialog__copy p,
:global(html.dark) .settings-guide-secondary__body p,
:global(html.dark) .settings-step-nav__copy span,
:global(html.dark) .settings-runtime-board__head p,
:global(html.dark) .settings-runtime-hub__head p,
:global(html.dark) .settings-config-card__note,
:global(html.dark) .settings-notes__state,
:global(html.dark) .settings-stage__desc,
:global(html.dark) .settings-form-card__desc,
:global(html.dark) .settings-helper,
:global(html.dark) .settings-note-list,
:global(html.dark) .settings-toggle,
:global(html.dark) .settings-runtime-status__model-row .text-\[11px\] {
  color: #94a3b8;
}

:global(html.dark) .settings-input {
  border-color: rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.03);
  color: rgba(255, 255, 255, 0.92);
}

:global(html.dark) .settings-input::placeholder {
  color: rgba(255, 255, 255, 0.32);
}

:global(html.dark) .settings-input:focus {
  border-color: rgba(129, 140, 248, 0.46);
  box-shadow: 0 0 0 4px rgba(79, 70, 229, 0.18);
}

:global(html.dark) .settings-primary-btn {
  box-shadow: 0 20px 38px rgba(37, 99, 235, 0.16);
}

:global(html.dark) .settings-ghost-btn:hover:not(:disabled),
:global(html.dark) .settings-secondary-btn:hover:not(:disabled),
:global(html.dark) .settings-step-nav__item:hover,
:global(html.dark) .settings-step-nav__item--active,
:global(html.dark) .settings-guide-step:hover,
:global(html.dark) .settings-guide-step--active,
:global(html.dark) .settings-guide-dialog__step:hover,
:global(html.dark) .settings-guide-dialog__step--active {
  border-color: rgba(129, 140, 248, 0.28);
  background: rgba(255, 255, 255, 0.06);
  box-shadow: 0 18px 36px rgba(0, 0, 0, 0.28);
  color: #e2e8f0;
}

:global(html.dark) .settings-status-chip--success {
  background: rgba(6, 95, 70, 0.34);
  color: #6ee7b7;
}

:global(html.dark) .settings-status-chip--warning {
  background: rgba(120, 53, 15, 0.34);
  color: #fcd34d;
}

:global(html.dark) .settings-alert--error {
  border-color: rgba(248, 113, 113, 0.24);
  background: rgba(127, 29, 29, 0.24);
  color: #fca5a5;
}

:global(html.dark) .settings-alert--success {
  border-color: rgba(16, 185, 129, 0.24);
  background: rgba(6, 78, 59, 0.28);
  color: #6ee7b7;
}

:global(html.dark) .settings-savebar {
  border-top-color: rgba(255, 255, 255, 0.08);
}

:global(html.dark) .settings-guide-panel__preview,
:global(html.dark) .settings-guide-dialog__viewport,
:global(html.dark) .settings-guide-secondary__media {
  border-color: rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
}

:global(html.dark) .settings-guide-panel__tips,
:global(html.dark) .settings-notes__body {
  border-top-color: rgba(255, 255, 255, 0.08);
}

:global(html.dark) .settings-guide-step__index {
  border-color: rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
  color: #cbd5e1;
}

:global(html.dark) .settings-guide-step__copy strong {
  color: rgba(255, 255, 255, 0.96);
}

:global(html.dark) .settings-guide-step__copy span {
  color: #94a3b8;
}

:global(html.dark) .settings-sensitive-item + .settings-sensitive-item {
  border-top-color: rgba(255, 255, 255, 0.08);
}
</style>
