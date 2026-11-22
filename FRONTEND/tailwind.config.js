/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        porcelain: '#FFFFFF',
        snow: '#F6F6F7',
        hairline: '#E6E6E9',
        graphite: {
          DEFAULT: '#25272D',
          muted: '#5F6368',
          subtle: '#8C9199',
          light: '#B2B6BC',
        },
        cardinal: {
          DEFAULT: '#C8102E',
          hover: '#A90D26',
          active: '#8E0B20',
          focus: 'rgba(200, 16, 46, 0.25)',
        },
        blush: {
          DEFAULT: '#FCEBED',
          hover: '#F9D8DC',
          active: '#F4C2C9',
        },
        status: {
          amber: '#B7791F',
          amberBg: '#FEF3C7',
          amberText: '#92400E',
          teal: '#1F7A5C',
          tealBg: '#D1FAE5',
          tealText: '#065F46',
          slate: '#6B7280',
          slateBg: '#F3F4F6',
          slateText: '#374151',
        }
      },
      fontFamily: {
        heading: ['"Bricolage Grotesque"', 'system-ui', 'sans-serif'],
        body: ['"Public Sans"', 'system-ui', 'sans-serif'],
      },
      borderRadius: {
        input: '6px',
        panel: '12px',
        pill: '9999px',
      },
      boxShadow: {
        subtle: '0 1px 3px 0 rgba(37, 39, 45, 0.04), 0 1px 2px -1px rgba(37, 39, 45, 0.03)',
        panel: '0 4px 6px -1px rgba(37, 39, 45, 0.03), 0 2px 4px -2px rgba(37, 39, 45, 0.02), 0 0 0 1px #E6E6E9',
        floating: '0 10px 15px -3px rgba(37, 39, 45, 0.05), 0 4px 6px -4px rgba(37, 39, 45, 0.03)',
      },
      animation: {
        'pulse-subtle': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      }
    },
  },
  plugins: [],
}
