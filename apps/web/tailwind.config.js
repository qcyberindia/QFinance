module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        cream: { 0: "#FBF8F1", 1: "#F3EDDD", 2: "#E9DFC6" },
        brass: { DEFAULT: "#A8863E", dark: "#7C6329" },
        ink: { DEFAULT: "#2B2621", soft: "#5B5347" },
        line: "#D8CBA9",
        up: "#4B6C4A",
        down: "#9C4B3F",
      },
      fontFamily: {
        display: ["Fraunces", "serif"],
        body: ["Inter", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
    },
  },
  plugins: [],
};
