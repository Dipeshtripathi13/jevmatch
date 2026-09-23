/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        display: ['Manrope', 'Inter', 'ui-sans-serif', 'system-ui'],
      },
      colors: {
        ink: '#101820',
        paper: '#f7f5ef',
        acid: '#c8f169',
        teal: '#087e73',
      },
      boxShadow: {
        lift: '0 24px 70px -30px rgb(15 35 35 / 0.35)',
      },
    },
  },
  plugins: [],
}
