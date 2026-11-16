/** Brand tokens come from CLAUDE.md (sampled from the official logo). Never use ad-hoc hex values. */
module.exports = {
  content: ["./templates/**/*.html", "./*/templates/**/*.html", "./*/forms.py", "./core/templatetags/*.py"],
  theme: {
    extend: {
      colors: {
        rlm: {
          black: "var(--rlm-black)",
          flame: "var(--rlm-flame)",
          "flame-deep": "var(--rlm-flame-deep)",
          "flame-dark": "var(--rlm-flame-dark)",
          amber: "var(--rlm-amber)",
          gold: "var(--rlm-gold)",
          white: "var(--rlm-white)",
          cream: "var(--rlm-cream)",
          ink: "var(--rlm-ink)",
          grey: "var(--rlm-grey)",
          line: "var(--rlm-line)",
        },
      },
      backgroundImage: {
        flame: "var(--rlm-flame-gradient)",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        display: ["Montserrat", "Inter", "system-ui", "sans-serif"],
      },
      maxWidth: { prose: "68ch" },
    },
  },
  plugins: [],
};
