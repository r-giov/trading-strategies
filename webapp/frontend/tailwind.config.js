/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        cyber: {
          bg: "#050510",
          surface: "#0a0a1f",
          border: "#1a1a3a",
          accent: "#00d4ff",
          purple: "#6c5ce7",
          text: "#c0c0d8",
          muted: "#505070",
          dim: "#3a3a5a",
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Share Tech Mono", "monospace"],
      },
      boxShadow: {
        glow: "0 0 15px rgba(0, 212, 255, 0.2), inset 0 0 15px rgba(0, 212, 255, 0.05)",
        "glow-lg": "0 0 30px rgba(0, 212, 255, 0.3)",
        "glow-purple": "0 0 15px rgba(108, 92, 231, 0.2)",
        "glow-green": "0 0 15px rgba(0, 255, 136, 0.2)",
        "glow-red": "0 0 15px rgba(255, 34, 85, 0.2)",
      },
    },
  },
  plugins: [],
};
