<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  result: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['copy'])

const activeTab = ref('corrected')
const showDiff = ref(false)

// 解析 inline diff 為高亮格式
const parsedDiff = computed(() => {
  const text = props.result.diff_inline
  const parts = []
  let current = ''
  let i = 0

  while (i < text.length) {
    if (text.substring(i, i + 2) === '[-') {
      if (current) {
        parts.push({ type: 'normal', text: current })
        current = ''
      }
      const end = text.indexOf('-]', i + 2)
      if (end !== -1) {
        parts.push({ type: 'remove', text: text.substring(i + 2, end) })
        i = end + 2
        continue
      }
    } else if (text.substring(i, i + 2) === '[+') {
      if (current) {
        parts.push({ type: 'normal', text: current })
        current = ''
      }
      const end = text.indexOf('+]', i + 2)
      if (end !== -1) {
        parts.push({ type: 'add', text: text.substring(i + 2, end) })
        i = end + 2
        continue
      }
    }
    current += text[i]
    i++
  }
  if (current) {
    parts.push({ type: 'normal', text: current })
  }
  return parts
})

function copyToClipboard() {
  const text = activeTab.value === 'corrected'
    ? props.result.corrected_text
    : props.result.original_text
  emit('copy', text)
}
</script>

<template>
  <section class="card">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h2 class="text-echo-blue font-semibold text-lg">轉錄結果</h2>
        <p class="text-sm text-text-primary/50 mt-1">
          {{ result.title }} · {{ result.channel }}
        </p>
      </div>

      <!-- Stats -->
      <div class="flex gap-4 text-sm">
        <div class="text-center">
          <div class="text-pulse-amber font-semibold text-lg">
            {{ (result.similarity_ratio * 100).toFixed(1) }}%
          </div>
          <div class="text-text-primary/50">相似度</div>
        </div>
        <div class="text-center">
          <div class="text-echo-blue font-semibold text-lg">
            {{ result.change_count }}
          </div>
          <div class="text-text-primary/50">變更處</div>
        </div>
      </div>
    </div>

    <!-- Tabs -->
    <div class="flex gap-2 mb-4 border-b border-soft-mist">
      <button
        @click="activeTab = 'corrected'"
        class="px-4 py-2 text-sm font-medium transition-colors relative"
        :class="activeTab === 'corrected' ? 'text-echo-blue' : 'text-text-primary/50 hover:text-text-primary'"
      >
        校正後
        <div
          v-if="activeTab === 'corrected'"
          class="absolute bottom-0 left-0 right-0 h-0.5 bg-echo-blue rounded-full"
        ></div>
      </button>
      <button
        @click="activeTab = 'original'"
        class="px-4 py-2 text-sm font-medium transition-colors relative"
        :class="activeTab === 'original' ? 'text-echo-blue' : 'text-text-primary/50 hover:text-text-primary'"
      >
        原始轉譯
        <div
          v-if="activeTab === 'original'"
          class="absolute bottom-0 left-0 right-0 h-0.5 bg-echo-blue rounded-full"
        ></div>
      </button>
      <button
        @click="showDiff = !showDiff"
        class="px-4 py-2 text-sm font-medium transition-colors ml-auto"
        :class="showDiff ? 'text-pulse-amber' : 'text-text-primary/50 hover:text-text-primary'"
      >
        {{ showDiff ? '隱藏差異' : '顯示差異' }}
      </button>
    </div>

    <!-- Content -->
    <div class="relative">
      <!-- Text Content -->
      <div
        v-if="!showDiff"
        class="bg-canvas rounded-xl p-6 max-h-96 overflow-y-auto text-text-primary leading-relaxed whitespace-pre-wrap"
      >
        {{ activeTab === 'corrected' ? result.corrected_text : result.original_text }}
      </div>

      <!-- Diff View -->
      <div
        v-else
        class="bg-canvas rounded-xl p-6 max-h-96 overflow-y-auto leading-relaxed"
      >
        <template v-for="(part, index) in parsedDiff" :key="index">
          <span v-if="part.type === 'normal'">{{ part.text }}</span>
          <span v-else-if="part.type === 'remove'" class="diff-remove">{{ part.text }}</span>
          <span v-else-if="part.type === 'add'" class="diff-add">{{ part.text }}</span>
        </template>
      </div>

      <!-- Copy Button -->
      <button
        @click="copyToClipboard"
        class="absolute top-3 right-3 p-2 bg-white rounded-lg border border-soft-mist hover:bg-soft-mist/50 transition-colors"
        title="複製到剪貼簿"
      >
        <svg class="w-4 h-4 text-text-primary/50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
        </svg>
      </button>
    </div>

    <!-- Language Badge -->
    <div class="mt-4 flex items-center gap-2">
      <span class="px-3 py-1 bg-echo-blue/10 text-echo-blue text-xs font-medium rounded-full">
        {{ result.language.toUpperCase() }}
      </span>
      <span class="text-xs text-text-primary/50">
        偵測語言
      </span>
    </div>
  </section>
</template>
