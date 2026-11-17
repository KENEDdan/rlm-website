# Performance and Lighthouse results

**Run:** 2026-11-16 · Lighthouse 12.2.1 · mobile profile with simulated slow 4G and CPU throttling
(Lighthouse default) · production image (gunicorn + WhiteNoise) behind a local Caddy with compression,
demo content loaded (`seed_demo`).

## Scores (after phase J fixes)

| Page | Performance | Accessibility | Best practices | SEO | LCP |
|---|---|---|---|---|---|
| Home `/` | 100 (3 repeat runs) | 100 | 76* | 100 | 1.7 s |
| Events `/events/` | 94–99 | 100 | 76* | 100 | 1.9 s |
| Album `/gallery/<album>/` | 100 | 100 | 76* | 100 | 1.9 s |
| Give `/give/` | 99 | 100 | 76* | 100 | 1.8 s |
| Contact `/contact/` | 99 | 100 | 76* | 100 | 1.8 s |

CLS is 0 on every page. Performance varies by a few points between runs due to CPU noise on the PC (one
cold run of Home scored 81 from a blocking-time spike; three repeats scored 100).

\* **Best practices 76 is caused only by testing over plain HTTP locally:** "does not use HTTPS", "does not
redirect HTTP to HTTPS", and one console message that the Cross-Origin-Opener-Policy header is ignored on
non-HTTPS origins. HTTP/2 also needs TLS. All of these clear once production serves HTTPS through Caddy
(phase K), with HSTS and the HTTPS redirect already configured in `config/settings/prod.py`.

## Sliders / carousels (2026-11-17)

**Setup:** same as above (Lighthouse 12.2.1, mobile, simulated slow 4G + 4x CPU), against the production
image running in the local rehearsal stack (`docker-compose.prod.yml`, Caddy, gunicorn, WhiteNoise), reached
over plain HTTP through a throwaway proxy. Medians of repeated runs; Best practices stays 76 only because of
plain-HTTP testing (see above).

| Page | Before (perf / a11y) | After, same content | After, realistic slider content* |
|---|---|---|---|
| Home `/` | 99 / 100 (TBT 80–110 ms, LCP 1.8 s) | 99 / 100 (TBT 0–40 ms, LCP 1.8 s) | 95 / 100 (runs 74–99, LCP 1.9 s) |
| About `/about/` | 100 / 100 | 100 / 100 | 91 / 100 (one run, noisy period) |
| Album `/gallery/<album>/` | 99 / 100 | 99 / 100 | 95 / 100 (one run, noisy period) |

CLS is 0 everywhere. \* 4 hero slides (3 with 1920x900 photos), 6 partner logos and 3 testimonies were added
temporarily to the rehearsal database for these runs and removed afterwards.

**Noise:** this PC runs other projects' containers. During the "realistic" runs the unchanged Events page
(no sliders) also dropped from 99 to 84 in one of four runs (TBT 610 ms), and the same home page used 1.6 s
of main-thread time in one run and 4.9 s in another. In quiet runs the slider's only long task is ~60 ms
(throttled). Re-measure on the real server after launch.

**Slider budget:** `static/js/slider.js` is ~4.3 KB gzipped (limit 10 KB, enforced by a test), no
dependencies. The first hero photo is preloaded with `fetchpriority="high"`; every other slider image is
lazy-loaded WebP with `srcset`; slides have fixed aspect ratios / minimum heights.

### Two pitfalls found and fixed while measuring (keep these when changing the slider)
1. **Lighthouse reported NO_LCP on the home page.** The first snap point of each card track sat 2 px in
   (the track's horizontal padding), so the browser *snapped* (= scrolled) every track on load, and Chrome
   discards the page's Largest Contentful Paint after a scroll. Fix: `scroll-padding-inline` equal to the
   padding (and `overflow-y: hidden`). See the comment on `.slider-track` in `static/css/input.css`.
2. **One long task of 250–490 ms (throttled) from slider start-up.** Each slider read layout
   (`offsetLeft`/`scrollWidth`) between DOM writes, forcing a full reflow per slider. Fix: start after the
   first frame, read all sliders' layout first, then write, autoplay on the next frame, partner strip in
   its own task. Home TBT went from 130–370 ms to 0–40 ms. The scrollbar is also never shown/hidden when
   JS starts (that would shift the page on desktop).

## Fixed in phase J

* Event pages jumped from `h1` to `h3` (heading order): added a section heading for screen readers.
* Header and footer logos now use `srcset` so small screens download smaller files.
* The large hero logo (desktop only) is lazy-loaded, so phones no longer download it.

## Remaining (minor)

* Footer logo: Lighthouse reports about 20 KiB possible savings on high-density phones (the 320 px file is
  chosen for a 112 px slot at 1.75× density). A 224 px rendition would save it; not worth the extra asset now.

## Why it is fast

Server-rendered HTML; one small CSS file (Tailwind, minified, hashed, cached for a year); htmx and a tiny
site script loaded with `defer`; self-hosted fonts with `font-display: swap`; WebP renditions at
480/960/1600 px with `srcset` and lazy loading; YouTube loads only when a visitor presses play; Brotli/gzip
from WhiteNoise and Caddy.

## How to re-run

The reusable image `rlm-lighthouse:local` (Node 22 + Chromium + Lighthouse, local only) was built from a
throwaway Dockerfile (see `docs/DECISIONS.md` D-008). Run the production image and a Caddy container on the
`rlm_internal` network as described in `docs/DEPLOYMENT.md`, then in Git Bash:

```bash
MSYS_NO_PATHCONV=1 docker run --rm --network rlm_internal -v "$(pwd -W)/lh:/reports" rlm-lighthouse:local \
  http://rlm-caddy/ --chrome-flags="--headless=new --no-sandbox" --output=html --output-path=/reports/home
```
Run each page two or three times and use the median.
