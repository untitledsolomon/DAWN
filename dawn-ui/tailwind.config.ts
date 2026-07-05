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
        // DAWN palette — warm neutral grey base, Claude-UI inspired
        abyss: "#F4F3F1",       // main background — warm light grey
        surface: "#FFFFFF",     // cards, sidebar
        elevated: "#EDEBE8",    // inputs, hover states
        rim: "#DDDAD5",         // borders
        dawn: "#0FA8A6",        // primary accent — cyan-teal
        ember: "#C96442",       // warm accent — terracotta (Claude-ish warm tone)
        text: {
          primary: "#2B2A27",   // near-black warm grey
          secondary: "#6B6862",
          muted: "#9C988F",
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
