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
