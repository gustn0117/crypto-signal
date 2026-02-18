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
        "card-hover": "#000613",

        primary: { DEFAULT: "#4680ff", dark: "#001646" },
        secondary: "#673bb7",

        success: { DEFAULT: "#26dad2", text: "#4caf50" },
        danger: { DEFAULT: "#ef5350", text: "#ff5722" },
        warning: { DEFAULT: "#ffb22b", text: "#ffc107" },
        info: { DEFAULT: "#1976d2", text: "#17a2b8" },

        heading: "#ffffff",
        "body-text": "#abafb3",
        "text-secondary": "#dddddd",
        muted: "#99abb4",
        "icon-muted": "#6a707e",

        border: "rgba(120, 130, 140, 0.13)",

        "sidebar-bg": "#0b0c21",
        "sidebar-active": "#10112d",
        "sidebar-accent": "#1976d2",
      },
      fontFamily: {
        sans: ["Roboto", "sans-serif"],
      },
      spacing: {
        sidebar: "240px",
        "sidebar-collapsed": "60px",
        header: "60px",
      },
      borderRadius: {
        card: "5px",
      },
      boxShadow: {
        card: "0 5px 20px rgba(0, 0, 0, 0.05)",
        sidebar: "1px 0 20px rgba(0, 0, 0, 0.08)",
        dropdown: "0 3px 12px rgba(0, 0, 0, 0.15)",
      },
    },
  },
  plugins: [],
};
export default config;
