import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // DAWN palette — deep navy-black base with cyan-teal accent
        abyss: "#060811",       // main background
        surface: "#0C1222",     // cards, sidebar
        elevated: "#112038",    // inputs, hover states
        rim: "#1E3357",         // borders
        dawn: "#3ECFCE",        // primary accent — cyan-teal
        ember: "#FF9F43",       // warm accent — amber
        text: {
          primary: "#E2EAF4",
          secondary: "#7B90B2",
          muted: "#3D5280",
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
        dawn: "0 0 20px rgba(62, 207, 206, 0.15)",
        ember: "0 0 20px rgba(255, 159, 67, 0.15)",
      },
    },
  },
  plugins: [],
};

export default config;
