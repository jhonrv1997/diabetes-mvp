/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#ebf4ff',
          100: '#d1e6ff',
          200: '#a9d1ff',
          300: '#72b4ff',
          400: '#3a91ff',
          500: '#2c5282',
          600: '#24476e',
          700: '#1c3a5a',
          800: '#142d46',
          900: '#0c1f32',
        },
        'risk-low': {
          light: '#e6f5ec',
          DEFAULT: '#47805a',
          dark: '#2d5a3a',
        },
        'risk-medium': {
          light: '#fef9e7',
          DEFAULT: '#9b8048',
          dark: '#6e5a30',
        },
        'risk-high': {
          light: '#fde8e6',
          DEFAULT: '#8e4f49',
          dark: '#6e3430',
        },
        background: '#f7fafc',
      },
      animation: {
        'pulse-alert': 'pulseAlert 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
      keyframes: {
        pulseAlert: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.6' },
        },
      },
    },
  },
  plugins: [],
}
