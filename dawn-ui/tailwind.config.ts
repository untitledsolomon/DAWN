import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      screens: {
        "xs": "480px",
      },
      fontSize: {
        "2xs": ["0.625rem", { lineHeight: "0.875rem" }], // 10px
      },
      colors: {
        // DAWN palette — cool neutral grey base, modern minimalist
        abyss: "#F7F7F8",       // main background — cool light grey
        surface: "#FFFFFF",     // cards, sidebar
        elevated: "#EEEEF0",    // inputs, hover states
        rim: "#E2E2E6",         // borders
        dawn: "#0E9BA8",        // primary accent — cool cyan-teal
        ember: "#C96442",       // warm accent — terracotta (kept for warmth)
        text: {
          primary: "#1F1F23",   // near-black cool grey
          secondary: "#5F5F66",
          muted: "#9A9AA3",
        },
      },
      fontFamily: {
        sans: ["var(--font-outfit)", "system-ui", "sans-serif"],
        mono: ["var(--font-jetbrains)", "monospace"],
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "scan": "scan 1.5s ease-in-out infinite",
        "fade-in": "fadeIn 0.2s ease-out",
        "slide-up": "slideUp 0.2s ease-out",
      },
      keyframes: {
        scan: {
          "0%, 100%": { opacity: "0.4" },
          "50%": { opacity: "1" },
        },
        fadeIn: {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        slideUp: {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      boxShadow: {
        dawn: "0 0 20px rgba(15, 168, 166, 0.10)",
        ember: "0 0 20px rgba(201, 100, 66, 0.10)",
        soft: "0 1px 3px rgba(43, 42, 39, 0.06), 0 1px 2px rgba(43, 42, 39, 0.04)",
      },
    },
  },
  plugins: [],
};

export default config;
