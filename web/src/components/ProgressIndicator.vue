<script setup>
defineProps({
  status: {
    type: Object,
    required: true
  }
})
</script>

<template>
  <section class="card">
    <div class="flex items-center gap-4 mb-4">
      <!-- Animated Icon -->
      <div class="relative w-12 h-12">
        <div class="absolute inset-0 bg-echo-blue/20 rounded-full animate-ping"></div>
        <div class="absolute inset-0 bg-echo-blue rounded-full flex items-center justify-center">
          <svg class="w-6 h-6 text-white animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
          </svg>
        </div>
      </div>

      <div class="flex-1">
        <h3 class="font-medium text-text-primary">{{ status.message }}</h3>
        <p class="text-sm text-text-primary/50">處理中，請稍候...</p>
      </div>

      <div class="text-2xl font-semibold text-echo-blue">
        {{ status.progress }}%
      </div>
    </div>

    <!-- Progress Bar -->
    <div class="progress-bar">
      <div
        class="progress-bar-fill"
        :style="{ width: `${status.progress}%` }"
      ></div>
    </div>

    <!-- Steps -->
    <div class="flex justify-between mt-4 text-xs text-text-primary/50">
      <span :class="{ 'text-echo-blue font-medium': status.progress >= 10 }">下載音訊</span>
      <span :class="{ 'text-echo-blue font-medium': status.progress >= 40 }">Whisper 轉錄</span>
      <span :class="{ 'text-echo-blue font-medium': status.progress >= 70 }">GPT 校正</span>
      <span :class="{ 'text-echo-blue font-medium': status.progress >= 90 }">完成</span>
    </div>
  </section>
</template>
