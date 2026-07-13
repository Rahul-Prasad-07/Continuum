# Continuum — Web

Production **Next.js 15** (App Router + TypeScript) migration of the Continuum
marketing site. The visual design, copy, animations and interactions are a
**byte-faithful** port of the original single-file `index.html` — nothing was
redesigned or rewritten.

## How the faithful migration works

The original `index.html` remains the single source of truth. At `predev` /
`prebuild`, `scripts/extract.mjs` splits it into three pieces:

| Piece                       | Destination            | Rendered as                                  |
| --------------------------- | ---------------------- | -------------------------------------------- |
| all `<style>` blocks        | `app/globals.css`      | imported once in the root layout             |
| body markup (no style/js)   | `generated/markup.ts`  | server-rendered verbatim (SSG, SEO-friendly) |
| the three `<script>` blocks | `generated/scripts.ts` | emitted inline after the markup, run natively |

`app/layout.tsx` owns the `<head>`: title/description/OpenGraph via the Next
Metadata API, `theme-color` via the Viewport export, the Fraunces font links,
the SVG favicon and the `SoftwareApplication` JSON-LD.

A `display:contents` wrapper around the injected markup keeps `#bgfx` fixed
positioning and stacking identical to the original, where the elements were
direct children of `<body>`.

> `generated/` is rebuilt from `index.html` on every dev/build and is
> git-ignored. To change the site, edit `index.html` and rerun — the migration
> stays a pure, reproducible transform.

## Develop

```bash
npm install
npm run dev      # http://localhost:3000  (runs extract first)
```

## Build & run

```bash
npm run build    # optimized production build (statically prerendered)
npm run start
```

## Deploy

Deploys to Vercel as a standard Next.js app (`vercel.json` → `framework: nextjs`).
The existing Vercel project link in `.vercel/` is preserved.
