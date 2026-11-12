/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        white: 'rgb(var(--text-primary-rgb) / <alpha-value>)',
        black: 'rgb(var(--shadow-color-rgb) / <alpha-value>)',
        gray: {'100': 'rgb(var(--text-secondary-rgb) / <alpha-value>)', '200': 'rgb(var(--text-secondary-rgb) / <alpha-value>)', '300': 'rgb(var(--text-secondary-rgb) / <alpha-value>)', '400': 'rgb(var(--text-muted-rgb) / <alpha-value>)', '500': 'rgb(var(--text-muted-rgb) / <alpha-value>)', '600': 'rgb(var(--text-muted-rgb) / <alpha-value>)', '700': 'rgb(var(--surface-rgb) / <alpha-value>)', '800': 'rgb(var(--surface-rgb) / <alpha-value>)', '900': 'rgb(var(--surface-rgb) / <alpha-value>)'},
        red: {'100': 'rgb(var(--error-rgb) / <alpha-value>)', '200': 'rgb(var(--error-rgb) / <alpha-value>)', '300': 'rgb(var(--error-rgb) / <alpha-value>)', '400': 'rgb(var(--error-rgb) / <alpha-value>)', '500': 'rgb(var(--error-rgb) / <alpha-value>)', '600': 'rgb(var(--error-rgb) / <alpha-value>)', '700': 'rgb(var(--error-rgb) / <alpha-value>)', '800': 'rgb(var(--error-rgb) / <alpha-value>)', '900': 'rgb(var(--error-rgb) / <alpha-value>)'},
        green: {'100': 'rgb(var(--success-rgb) / <alpha-value>)', '200': 'rgb(var(--success-rgb) / <alpha-value>)', '300': 'rgb(var(--success-rgb) / <alpha-value>)', '400': 'rgb(var(--success-rgb) / <alpha-value>)', '500': 'rgb(var(--success-rgb) / <alpha-value>)', '600': 'rgb(var(--success-rgb) / <alpha-value>)', '700': 'rgb(var(--success-rgb) / <alpha-value>)', '800': 'rgb(var(--success-rgb) / <alpha-value>)', '900': 'rgb(var(--success-rgb) / <alpha-value>)'},
        yellow: {'100': 'rgb(var(--warning-rgb) / <alpha-value>)', '200': 'rgb(var(--warning-rgb) / <alpha-value>)', '300': 'rgb(var(--warning-rgb) / <alpha-value>)', '400': 'rgb(var(--warning-rgb) / <alpha-value>)', '500': 'rgb(var(--warning-rgb) / <alpha-value>)', '600': 'rgb(var(--warning-rgb) / <alpha-value>)', '700': 'rgb(var(--warning-rgb) / <alpha-value>)', '800': 'rgb(var(--warning-rgb) / <alpha-value>)', '900': 'rgb(var(--warning-rgb) / <alpha-value>)'},
        amber: {'100': 'rgb(var(--warning-rgb) / <alpha-value>)', '200': 'rgb(var(--warning-rgb) / <alpha-value>)', '300': 'rgb(var(--warning-rgb) / <alpha-value>)', '400': 'rgb(var(--warning-rgb) / <alpha-value>)', '500': 'rgb(var(--warning-rgb) / <alpha-value>)', '600': 'rgb(var(--warning-rgb) / <alpha-value>)', '700': 'rgb(var(--warning-rgb) / <alpha-value>)', '800': 'rgb(var(--warning-rgb) / <alpha-value>)', '900': 'rgb(var(--warning-rgb) / <alpha-value>)'},

        dark: 'rgb(var(--background-rgb) / <alpha-value>)',
        card: 'rgb(var(--surface-rgb) / <alpha-value>)',
        accent: 'rgb(var(--accent-rgb) / <alpha-value>)',
        border: 'rgb(var(--border-rgb) / <alpha-value>)',
      },
    },
  },
  plugins: [],
}
