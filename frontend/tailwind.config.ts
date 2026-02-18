import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        body: "#070713",
        card: "#0b0c21",
        "card-active": "#10112d",
        "card-hover": "#0d0e24",

        primary: { DEFAULT: "#4680ff", dark: "#001646" },
        secondary: "#673bb7",

        success: { DEFAULT: "#26dad2", text: "#4caf50" },
        danger: { DEFAULT: "#ef5350", text: "#ff5722" },
        warning: { DEFAULT: "#ffb22b", text: "#ffc107" },
        info: { DEFAULT: "#1976d2", text: "#17a2b8" },

        // 시맨틱 시그널 컬러
        long: { DEFAULT: "#26dad2", muted: "rgba(38,218,210,0.12)" },
        short: { DEFAULT: "#ef5350", muted: "rgba(239,83,80,0.12)" },
        profit: "#4caf50",
        loss: "#ef5350",

        heading: "#ffffff",
        "body-text": "#abafb3",
        "text-secondary": "#dddddd",
        muted: "#99abb4",
        "icon-muted": "#6a707e",

        border: "rgba(120, 130, 140, 0.13)",

        "sidebar-bg": "#0a0b1e",
        "sidebar-active": "#10112d",
        "sidebar-accent": "#4680ff",
      },
      fontFamily: {
        sans: ["Roboto", "sans-serif"],
      },
      spacing: {
        sidebar: "240px",
        "sidebar-collapsed": "60px",
        header: "56px",
      },
      borderRadius: {
        card: "8px",
      },
      boxShadow: {
        card: "0 2px 8px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.03)",
        sidebar: "1px 0 20px rgba(0, 0, 0, 0.15)",
        dropdown: "0 4px 20px rgba(0, 0, 0, 0.3)",
      },
    },
  },
  plugins: [],
};
export default config;
