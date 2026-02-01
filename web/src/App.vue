<script setup>
import { ref, computed, watch } from 'vue'
import axios from 'axios'
import VideoInfo from './components/VideoInfo.vue'
import TranscriptResult from './components/TranscriptResult.vue'
import ProgressIndicator from './components/ProgressIndicator.vue'

// API base URL - 從環境變數取得，預設為同網域 /api（Docker 部署用）
const API_BASE = import.meta.env.VITE_API_BASE || ''

// 狀態
const videoUrl = ref('')
const videoInfo = ref(null)
const taskId = ref(null)
const taskStatus = ref(null)
const result = ref(null)
const loading = ref(false)
const error = ref(null)

// 選項
const language = ref('')
const skipCorrection = ref(false)
const customTerms = ref('')

// 步驟
const currentStep = computed(() => {
  if (result.value) return 3
  if (taskId.value) return 2
  if (videoInfo.value) return 1
  return 0
})

// 擷取影片資訊
async function fetchVideoInfo() {
  if (!videoUrl.value.trim()) return

  loading.value = true
  error.value = null
  videoInfo.value = null
  result.value = null
  taskId.value = null
  taskStatus.value = null

  try {
    const response = await axios.post(`${API_BASE}/api/video/info`, {
      url: videoUrl.value
    })
    videoInfo.value = response.data
  } catch (e) {
    error.value = e.response?.data?.detail || '無法擷取影片資訊'
  } finally {
    loading.value = false
  }
}

// 開始轉錄
async function startTranscription() {
  loading.value = true
  error.value = null

  try {
    const terms = customTerms.value
      .split(',')
      .map(t => t.trim())
      .filter(t => t)

    const response = await axios.post(`${API_BASE}/api/transcribe`, {
      url: videoUrl.value,
      language: language.value || null,
      skip_correction: skipCorrection.value,
      custom_terms: terms.length > 0 ? terms : null
    })

    taskId.value = response.data.task_id
    pollTaskStatus()
  } catch (e) {
    error.value = e.response?.data?.detail || '無法開始轉錄'
    loading.value = false
  }
}

// 輪詢任務狀態
async function pollTaskStatus() {
  if (!taskId.value) return

  try {
    const response = await axios.get(`${API_BASE}/api/task/${taskId.value}`)
    taskStatus.value = response.data

    if (response.data.status === 'completed') {
      result.value = response.data.result
      loading.value = false
    } else if (response.data.status === 'failed') {
      error.value = response.data.message
      loading.value = false
    } else {
      // 繼續輪詢
      setTimeout(pollTaskStatus, 1000)
    }
  } catch (e) {
    error.value = '無法取得任務狀態'
    loading.value = false
  }
}

// 重置
function reset() {
  videoUrl.value = ''
  videoInfo.value = null
  taskId.value = null
  taskStatus.value = null
  result.value = null
  error.value = null
  language.value = ''
  skipCorrection.value = false
  customTerms.value = ''
}

// 複製文字
function copyText(text) {
  navigator.clipboard.writeText(text)
}
</script>

<template>
  <div class="min-h-screen bg-canvas">
    <!-- Header -->
    <header class="border-b border-soft-mist bg-white/50 backdrop-blur-sm sticky top-0 z-10">
      <div class="max-w-4xl mx-auto px-6 py-4 flex items-center justify-between">
        <div class="flex items-center gap-3">
          <div class="w-8 h-8 bg-echo-blue rounded-xl flex items-center justify-center">
            <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
            </svg>
          </div>
          <h1 class="text-lg font-semibold text-text-primary">YouTube Transcripter</h1>
        </div>
        <span class="text-sm text-text-primary/50">Powered by Azetry</span>
      </div>
    </header>

    <!-- Main Content -->
    <main class="max-w-4xl mx-auto px-6 py-12">
      <!-- URL Input Section -->
      <section class="card mb-8">
        <h2 class="text-echo-blue font-semibold mb-4">輸入 YouTube 網址</h2>
        <div class="flex gap-3">
          <input
            v-model="videoUrl"
            type="text"
            class="input flex-1"
            placeholder="https://www.youtube.com/watch?v=..."
            @keyup.enter="fetchVideoInfo"
            :disabled="loading"
          />
          <button
            @click="fetchVideoInfo"
            class="btn-primary whitespace-nowrap"
            :disabled="loading || !videoUrl.trim()"
          >
            <span v-if="loading && !taskId">擷取中...</span>
            <span v-else>擷取資訊</span>
          </button>
        </div>

        <!-- Error Message -->
        <div v-if="error" class="mt-4 p-4 bg-red-50 border border-red-200 rounded-xl text-red-700">
          {{ error }}
        </div>
      </section>

      <!-- Video Info Section -->
      <VideoInfo
        v-if="videoInfo"
        :info="videoInfo"
        class="mb-8"
      />

      <!-- Options & Start Section -->
      <section v-if="videoInfo && !taskId" class="card mb-8">
        <h2 class="text-echo-blue font-semibold mb-4">轉錄選項</h2>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          <div>
            <label class="block text-sm font-medium text-text-primary/70 mb-2">
              指定語言（選填）
            </label>
            <select v-model="language" class="input">
              <option value="">自動偵測</option>
              <option value="zh">中文</option>
              <option value="en">英文</option>
              <option value="ja">日文</option>
              <option value="ko">韓文</option>
            </select>
          </div>

          <div>
            <label class="block text-sm font-medium text-text-primary/70 mb-2">
              專有名詞（逗號分隔）
            </label>
            <input
              v-model="customTerms"
              type="text"
              class="input"
              placeholder="OpenAI, ChatGPT, Whisper"
            />
          </div>
        </div>

        <div class="flex items-center gap-3 mb-6">
          <input
            type="checkbox"
            id="skipCorrection"
            v-model="skipCorrection"
            class="w-4 h-4 rounded border-soft-mist text-echo-blue focus:ring-echo-blue"
          />
          <label for="skipCorrection" class="text-sm text-text-primary/70">
            跳過 GPT 校正（僅使用 Whisper 原始轉譯）
          </label>
        </div>

        <button @click="startTranscription" class="btn-accent w-full">
          開始轉錄
        </button>
      </section>

      <!-- Progress Section -->
      <ProgressIndicator
        v-if="taskStatus && taskStatus.status !== 'completed'"
        :status="taskStatus"
        class="mb-8"
      />

      <!-- Result Section -->
      <TranscriptResult
        v-if="result"
        :result="result"
        @copy="copyText"
        class="mb-8"
      />

      <!-- Reset Button -->
      <div v-if="result" class="text-center">
        <button @click="reset" class="text-echo-blue hover:underline">
          處理另一個影片
        </button>
      </div>
    </main>

    <!-- Footer -->
    <footer class="border-t border-soft-mist py-6 mt-12">
      <div class="max-w-4xl mx-auto px-6 text-center text-sm text-text-primary/50">
        讓智慧累積，煩事一次完成。
      </div>
    </footer>
  </div>
</template>
