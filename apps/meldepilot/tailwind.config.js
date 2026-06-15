/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // tarifhub brand cyan — reporting / quality-data module.
        brand: {
          DEFAULT: "#0891b2",
          dark: "#155e75",
        },
      },
    },
  },
  plugins: [],
};
