import { fileURLToPath } from "node:url";
import { defineCollection } from "astro:content";
import { docsSchema } from "@astrojs/starlight/schema";
import { glob } from "astro/loaders";

// Docs live in src/content/docs. examples/** are copy-paste reference files
// (runbook manifests, scripts, prompts) — kept in the tree but not routed.
const docsRoot = fileURLToPath(new URL("./content/docs", import.meta.url));

export const collections = {
  docs: defineCollection({
    loader: glob({
      pattern: ["**/*.{md,mdx}", "!examples/**"],
      base: docsRoot,
    }),
    schema: docsSchema(),
  }),
};
