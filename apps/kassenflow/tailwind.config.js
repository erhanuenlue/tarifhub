/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // TarifHub brand sky — payer/correspondence module.
        brand: {
          DEFAULT: "#0ea5e9",
          dark: "#0369a1",
        },
      },
    },
  },
  plugins: [],
};
