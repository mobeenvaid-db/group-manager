/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        db: {
          red: '#FF3621',
          'red-dark': '#E02E1A',
          navy: '#1C2536',
          'navy-light': '#2A3650',
          slate: '#6B7A99',
        },
      },
    },
  },
  plugins: [],
};
