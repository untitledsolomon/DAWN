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
        // DAWN palette — warm neutral base, modern minimalist (dawn-preview)
        abyss: "#FBFBFA",       // main background
        surface: "#FFFFFF",     // cards, sidebar
        elevated: "#F5F5F3",    // inputs, hover states, elevated surfaces
        rim: "#E4E4E2",         // borders
        dawn: "#15807A",        // primary accent — deep teal
        ember: "#B84D3B",       // destructive/warning — terracotta
        amber: "#A66A00",       // warning amber
        success: "#15807A",     // healthy / positive (teal)
        error: "#B84D3B",       // unhealthy / negative (ember)
        text: {
          primary: "#16171A",   // near-black warm grey
          secondary: "#5F5F66",
          muted: "#929298",
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
        dawn: "0 0 20px rgba(21, 128, 122, 0.10)",
        ember: "0 0 20px rgba(184, 77, 59, 0.10)",
        soft: "0 1px 2px rgba(20, 20, 20, 0.025)",
      },
      borderRadius: {
        // Standardized radius scale (dawn-preview): 10px standard, 8px nested
        DEFAULT: "10px",
        card: "10px",
        nested: "8px",
        pill: "9999px",
      },
    },
  },
  plugins: [],
};

export default config;
