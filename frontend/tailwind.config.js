/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: '#0a0e1a',
        secondary: '#111827',
        card: '#1a2035',
        'card-hover': '#1e2642',
        border: '#2a3354',
        accent: '#6366f1',
        'accent-hover': '#818cf8',
        'accent-glow': 'rgba(99, 102, 241, 0.3)',
        green: '#10b981',
        'green-glow': 'rgba(16, 185, 129, 0.15)',
        red: '#ef4444',
        'red-glow': 'rgba(239, 68, 68, 0.15)',
        gold: '#f59e0b',
        silver: '#94a3b8',
        bronze: '#d97706',
        muted: '#5a6580',
        'text-primary': '#f0f2f5',
        'text-secondary': '#8b95b0',
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
      },
      keyframes: {
        flashGreen: {
          '0%': { backgroundColor: 'rgba(16, 185, 129, 0.15)' },
          '100%': { backgroundColor: 'transparent' },
        },
        flashRed: {
          '0%': { backgroundColor: 'rgba(239, 68, 68, 0.15)' },
          '100%': { backgroundColor: 'transparent' },
        },
        toastIn: {
          '0%': { opacity: '0', transform: 'translateX(100px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        toastOut: {
          '0%': { opacity: '1', transform: 'translateX(0)' },
          '100%': { opacity: '0', transform: 'translateX(100px)' },
        }
      },
      animation: {
        flashGreen: 'flashGreen 1.5s ease',
        flashRed: 'flashRed 1.5s ease',
        toastIn: 'toastIn 0.4s ease',
        toastOut: 'toastOut 0.4s ease 3.6s forwards',
      }
    },
  },
  plugins: [],
}
