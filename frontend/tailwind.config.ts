import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        chip: {
          bg: "#0a0e14",
          panel: "#111820",
          border: "#1e2a3a",
          grid: "#151c28",
          accent: "#00e5a0",
          accent2: "#00b4d8",
          warn: "#ffb020",
          danger: "#ff4757",
          text: "#c8d6e5",
          muted: "#6b7c93",
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
