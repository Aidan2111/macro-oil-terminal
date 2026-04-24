// Local-only mock for `next/font/google` network fetches. Used when
// building inside a sandbox that blocks fonts.googleapis.com. Wired
// up via NEXT_FONT_GOOGLE_MOCKED_RESPONSES at build time. Never
// required in shipping code — the real Google fetch runs in CI.
/* eslint-disable */
const INTER_CSS = `
@font-face {
  font-family: 'Inter Fallback';
  font-style: normal;
  font-weight: 400;
  src: url(data:font/woff2;base64,) format('woff2');
  unicode-range: U+0000-00FF;
}
`.trim();

module.exports = {
  "https://fonts.googleapis.com/css2?family=Inter:wght@100..900&display=swap":
    INTER_CSS,
};
