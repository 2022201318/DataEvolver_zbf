/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Outfit', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      colors: {
        /* 多模态数据准备 主色：青/橙双轨、科技感 */
        de: {
          cyan: '#00e5c8',
          'cyan-dim': '#00e5c860',
          'cyan-glow': '#00e5c820',
          teal: '#00b4d8',
          orange: '#ff8c42',
          'orange-dim': '#ff8c4260',
          magenta: '#e040fb',
          green: '#4ceb9a',
          red: '#ff5c6a',
        },
        brand: {
          50: '#e6fffa',
          100: '#b2f5e8',
          200: '#00e5c8',
          300: '#00b4d8',
          400: '#00a0b8',
          500: '#00e5c8',
          600: '#00b4d8',
          700: '#0d9488',
          800: '#115e59',
          900: '#134e4a',
          950: '#042f2e',
        },
        surface: {
          700: '#1a2a3a',
          800: '#0c1219',
          900: '#111a24',
          950: '#06090f',
        },
      },
      animation: {
        'pulse-dot': 'pulse-dot 2s ease-in-out infinite',
        'dataflow': 'dataflow 1s linear infinite',
        'glow-pulse': 'glow-pulse 2s ease-in-out infinite',
      },
      keyframes: {
        'pulse-dot': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.4' },
        },
        'dataflow': {
          '0%': { strokeDashoffset: '20' },
          '100%': { strokeDashoffset: '0' },
        },
        'glow-pulse': {
          '0%, 100%': { opacity: '0.3', filter: 'drop-shadow(0 0 3px rgba(0,229,200,0.3))' },
          '50%': { opacity: '0.8', filter: 'drop-shadow(0 0 8px rgba(0,229,200,0.5))' },
        },
      },
    },
  },
  plugins: [],
}
