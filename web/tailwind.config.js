/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Azetry Brand Colors
        'canvas': '#F8F9FA',
        'echo-blue': '#2563EB',
        'pulse-amber': '#F59E0B',
        'soft-mist': '#E5E7EB',
        'text-primary': '#1F2937',
      },
      fontFamily: {
        'sans': ['Inter', 'Noto Sans TC', 'sans-serif'],
      },
      borderRadius: {
        'xl': '12px',
        '2xl': '16px',
        '3xl': '24px',
      },
      backdropBlur: {
        'glass': '20px',
      },
    },
  },
  plugins: [],
}
