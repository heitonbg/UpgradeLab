/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        dark: '#101114',
        card: '#181a1f',
        accent: '#e9bc78',
        border: '#30333b',
      },
    },
  },
  plugins: [],
}
