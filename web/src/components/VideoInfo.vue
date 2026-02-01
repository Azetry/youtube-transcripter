<script setup>
defineProps({
  info: {
    type: Object,
    required: true
  }
})

function formatNumber(num) {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M'
  }
  if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K'
  }
  return num.toLocaleString()
}
</script>

<template>
  <section class="card">
    <div class="flex gap-6">
      <!-- Thumbnail -->
      <div class="flex-shrink-0">
        <img
          :src="info.thumbnail_url"
          :alt="info.title"
          class="w-48 h-28 object-cover rounded-xl"
        />
      </div>

      <!-- Info -->
      <div class="flex-1 min-w-0">
        <h3 class="font-semibold text-text-primary text-lg mb-2 truncate">
          {{ info.title }}
        </h3>

        <p class="text-text-primary/70 text-sm mb-3">
          {{ info.channel }}
        </p>

        <div class="flex flex-wrap gap-4 text-sm text-text-primary/60">
          <div class="flex items-center gap-1.5">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>{{ info.duration_formatted }}</span>
          </div>

          <div class="flex items-center gap-1.5">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
            </svg>
            <span>{{ formatNumber(info.view_count) }} 次觀看</span>
          </div>

          <div class="flex items-center gap-1.5">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            <span>{{ info.upload_date }}</span>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
