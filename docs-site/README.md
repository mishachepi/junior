# Junior docs site

[Astro](https://astro.build) + [Starlight](https://starlight.astro.build) site
published to <https://junior.mchep.dev> via GitHub Pages
(`.github/workflows/docs.yml`).

## Source of truth

All Markdown content lives in [`src/content/docs/`](src/content/docs). The
content collection loads it with a `glob` loader (`src/content.config.ts`, base
`./content/docs`, `examples/**` excluded — those are copy-paste reference
manifests / scripts / prompts, kept in the tree but not routed; doc links to
them point at the GitHub repo).

Authoring rules for `src/content/docs/*.md`:

- Each page needs a `title` in YAML frontmatter (Starlight renders it as the
  page H1; a custom remark plugin strips the body `# H1` so it isn't doubled).
- Cross-link with relative `*.md` paths. A remark plugin rewrites them to
  Starlight routes at build time.
- Callouts use GitHub alert syntax (`> [!NOTE]`, `> [!WARNING]`, `> [!TIP]`),
  which renders on GitHub and as Starlight asides.
- ```` ```mermaid ```` fenced blocks render client-side.

Navigation is configured in `astro.config.mjs` (`starlight.sidebar`).

## Commands

```bash
npm install        # install deps
npm run dev        # dev server on http://127.0.0.1:8181
npm run build      # static build -> dist/
npm run preview    # preview the build on http://127.0.0.1:8181
```
