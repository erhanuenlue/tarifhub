/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Matches the teal accent used by the arc42 docs site (mkdocs material).
        brand: {
          DEFAULT: "#0d9488",
          dark: "#0f766e",
        },
      },
    },
  },
  plugins: [],
};
