import { ref } from 'vue'
import { speechToText, textToSpeech } from '../services/interview'

let sharedAudioCtx: AudioContext | null = null

function getSharedAudioContext() {
  if (!sharedAudioCtx) {
    sharedAudioCtx = new AudioContext()
  }
  return sharedAudioCtx
}

export async function primeVoicePlayback(): Promise<void> {
  const audioCtx = getSharedAudioContext()
  if (audioCtx.state === 'suspended') {
    await audioCtx.resume()
  }
}

/**
 * 语音交互 composable
 * - 录音：MediaRecorder -> PCM -> 后端 STT
 * - 播放：后端 TTS -> WAV -> AudioContext 播放
 */
export function useVoice() {
  const isRecording = ref(false)
  const isPlaying = ref(false)
  const sttLoading = ref(false)
  const micPermission = ref<'unknown' | 'prompt' | 'granted' | 'denied'>('unknown')

  let mediaRecorder: MediaRecorder | null = null
  let audioChunks: Blob[] = []
  let currentAudioSource: AudioBufferSourceNode | null = null

  const audioConstraints: MediaTrackConstraints = {
    sampleRate: 16000,
    channelCount: 1,
    echoCancellation: true,
    noiseSuppression: true,
  }

  async function getPermissionState(): Promise<'unknown' | 'prompt' | 'granted' | 'denied'> {
    try {
      if (!('permissions' in navigator) || !navigator.permissions?.query) {
        return micPermission.value
      }
      const status = await navigator.permissions.query({ name: 'microphone' as PermissionName })
      const nextState = status.state as 'prompt' | 'granted' | 'denied'
      micPermission.value = nextState
      return nextState
    } catch {
      return micPermission.value
    }
  }

  async function ensureMicrophonePermission(): Promise<'already_granted' | 'granted_after_prompt'> {
    const stateBeforeRequest = await getPermissionState()
    if (stateBeforeRequest === 'granted') {
      micPermission.value = 'granted'
      return 'already_granted'
    }

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: audioConstraints,
    })
    stream.getTracks().forEach((track) => track.stop())
    micPermission.value = 'granted'

    return stateBeforeRequest === 'prompt' || stateBeforeRequest === 'unknown'
      ? 'granted_after_prompt'
      : 'already_granted'
  }

  async function startRecording(): Promise<void> {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: audioConstraints,
    })

    audioChunks = []
    mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' })

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.push(e.data)
    }

    mediaRecorder.start()
    micPermission.value = 'granted'
    isRecording.value = true
  }

  async function stopRecordingAndRecognize(): Promise<string> {
    return new Promise((resolve, reject) => {
      if (!mediaRecorder || mediaRecorder.state === 'inactive') {
        reject(new Error('未在录音'))
        return
      }

      mediaRecorder.onstop = async () => {
        mediaRecorder?.stream.getTracks().forEach((track) => track.stop())

        const webmBlob = new Blob(audioChunks, { type: 'audio/webm' })

        sttLoading.value = true
        try {
          const pcmBlob = await webmToPcm16k(webmBlob)
          const text = await speechToText(pcmBlob, 'pcm', 16000)
          resolve(text)
        } catch (e) {
          reject(e)
        } finally {
          sttLoading.value = false
          isRecording.value = false
        }
      }

      mediaRecorder.stop()
    })
  }

  async function webmToPcm16k(webmBlob: Blob): Promise<Blob> {
    const arrayBuf = await webmBlob.arrayBuffer()
    const tempCtx = new AudioContext()
    const audioBuf = await tempCtx.decodeAudioData(arrayBuf)
    await tempCtx.close()

    const offlineCtx = new OfflineAudioContext(1, audioBuf.duration * 16000, 16000)
    const source = offlineCtx.createBufferSource()
    source.buffer = audioBuf
    source.connect(offlineCtx.destination)
    source.start()
    const rendered = await offlineCtx.startRendering()

    const float32 = rendered.getChannelData(0)
    const int16 = new Int16Array(float32.length)
    for (let i = 0; i < float32.length; i++) {
      const sample = Math.max(-1, Math.min(1, float32[i] ?? 0))
      int16[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff
    }
    return new Blob([int16.buffer], { type: 'audio/pcm' })
  }

  async function playTTS(text: string, per?: number, spd?: number): Promise<void> {
    if (!text.trim()) return
    stopPlayback()

    isPlaying.value = true
    try {
      const audioCtx = getSharedAudioContext()
      if (audioCtx.state === 'suspended') {
        await audioCtx.resume()
      }
      const wavBuffer = await textToSpeech(text, per, spd)
      const audioBuf = await audioCtx.decodeAudioData(wavBuffer)

      currentAudioSource = audioCtx.createBufferSource()
      currentAudioSource.buffer = audioBuf
      currentAudioSource.connect(audioCtx.destination)
      currentAudioSource.onended = () => {
        isPlaying.value = false
      }
      currentAudioSource.start()
    } catch (e) {
      isPlaying.value = false
      throw e
    }
  }

  function stopPlayback() {
    if (currentAudioSource) {
      try {
        currentAudioSource.stop()
      } catch {
        // already stopped
      }
      currentAudioSource = null
    }
    isPlaying.value = false
  }

  return {
    isRecording,
    isPlaying,
    sttLoading,
    micPermission,
    ensureMicrophonePermission,
    startRecording,
    stopRecordingAndRecognize,
    playTTS,
    stopPlayback,
  }
}
