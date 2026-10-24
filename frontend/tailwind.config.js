/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        dark: '#0e0f12',
        card: '#16181d',
        accent: '#7cf5a8',
        border: '#23262d',
      },
    },
  },
  plugins: [],
}