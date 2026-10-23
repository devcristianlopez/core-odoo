import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        canvas: '#0b0d12',
        surface: {
          DEFAULT: '#11151c',
          raised: '#161d27',
          overlay: '#1c2430',
          muted: '#0e1219',
        },
        edge: {
          DEFAULT: '#28303d',
          muted: '#1e2531',
          strong: '#3a4454',
        },
        brand: {
          50: '#f7f2f6',
          100: '#ecdfe8',
          200: '#d9bed0',
          300: '#bd94b0',
          400: '#a06e90',
          500: '#865274',
          600: '#714b67',
          700: '#5d3d55',
          800: '#4c3345',
          900: '#3e2b39',
        },
        accent: {
          50: '#e8f8f7',
          100: '#c5eeeb',
          200: '#91dfda',
          300: '#5bcec7',
          400: '#2fb8b1',
          500: '#00a09d',
          600: '#017e84',
          700: '#02656a',
          800: '#045055',
          900: '#043f43',
        },
        danger: {
          400: '#f47676',
          500: '#e5484d',
          600: '#c53036',
          900: '#3d1719',
        },
        warning: {
          400: '#f5b74e',
          500: '#e69b23',
          900: '#3b2a0d',
        },
        success: {
          400: '#4ecb8d',
          500: '#22a06b',
          900: '#0f2f22',
        },
      },
      fontFamily: {
        sans: [
          'Inter',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'Roboto',
          'Helvetica Neue',
          'Arial',
          'sans-serif',
        ],
        mono: [
          'ui-monospace',
          'SFMono-Regular',
          'Menlo',
          'Monaco',
          'Consolas',
          'Liberation Mono',
          'monospace',
        ],
      },
      boxShadow: {
        card: '0 1px 0 0 rgba(255,255,255,0.03) inset, 0 10px 30px -18px rgba(0,0,0,0.9)',
        glow: '0 0 0 1px rgba(0,160,157,0.25), 0 12px 40px -18px rgba(0,160,157,0.55)',
      },
      keyframes: {
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        'slide-up': {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-in-right': {
          from: { opacity: '0', transform: 'translateX(16px)' },
          to: { opacity: '1', transform: 'translateX(0)' },
        },
        'slide-in-left': {
          from: { opacity: '0', transform: 'translateX(-16px)' },
          to: { opacity: '1', transform: 'translateX(0)' },
        },
        'pulse-soft': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.45' },
        },
      },
      animation: {
        'fade-in': 'fade-in 150ms ease-out',
        'slide-up': 'slide-up 180ms ease-out',
        'slide-in-right': 'slide-in-right 180ms ease-out',
        'slide-in-left': 'slide-in-left 180ms ease-out',
        'pulse-soft': 'pulse-soft 2s ease-in-out infinite',
      },
    },
  },
  plugins: [],
} satisfies Config
