/** Brand tokens: EXACTLY the palette in CLAUDE.md (sampled from the official logo), mirrored as CSS
 * variables in static/css/input.css. Hex values live only here and there; templates use token classes. */
module.exports = {
  content: ["./templates/**/*.html", "./*/templates/**/*.html", "./*/forms.py", "./core/templatetags/*.py"],
  theme: {
    extend: {
      colors: {
        rlm: {
          black: "#0A0A0A",
          flame: "#F0652A",
          "flame-deep": "#EE362C",
          "flame-dark": "#C2410C",
          amber: "#F3A831",
          gold: "#F8C124",
          white: "#FFFFFF",
          cream: "#FFF8F2",
          ink: "#1C1C1C",
          grey: "#6B6B6B",
          line: "#E8E8E8",
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
