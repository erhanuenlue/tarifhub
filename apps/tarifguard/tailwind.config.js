/** @type {import('tailwindcss').Config} */
// Brand theme mirrored verbatim from docs/brand/tokens.css (original Convergence
// identity, owner-canonical). The visual law lives in app/globals.css. Do not add
// colours or fonts here that are not in tokens.css — the palette is closed.
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        sky: "#0EA5E9", // brand signal: accents, highlights — not a text carrier
        navy: "#0C4A6E", // ink: headlines, frozen values, dark surfaces
        blue: "#2563EB", // interactive: buttons/links with white text (WCAG-safe)
        cyan: "#06B6D4", // stream accent · TarifIQ wayfinding
        "blue-stream": "#3B82F6", // stream accent · TarifCore wayfinding
        body: "#475569", // body text (slate)
        muted: "#94A3B8",
        "ink-black": "#0F172A",
        bg: "#F8FAFC",
        card: "#FFFFFF",
        line: "#E2E8F0",
        "sky-tint": "#E0F2FE", // chip-version background (tokens.css)
        success: "#059669",
        warning: "#D97706",
        error: "#DC2626",
      },
      fontFamily: {
        sans: ["Inter", "Helvetica Neue", "Arial", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
    },
  },
  plugins: [],
};
