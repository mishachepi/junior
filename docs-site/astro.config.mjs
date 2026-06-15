import { fileURLToPath } from "node:url";
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

import remarkStripTitle from "./plugins/remark-strip-title.mjs";
import remarkRewriteLinks from "./plugins/remark-rewrite-links.mjs";
import remarkMermaid from "./plugins/remark-mermaid.mjs";

const docsRoot = fileURLToPath(new URL("./src/content/docs", import.meta.url));
const repoUrl = "https://github.com/mishachepi/junior";
const docsDir = "docs-site/src/content/docs"; // path within the repo (for examples → GitHub links)

// Client-side mermaid rendering with light/dark theme sync.
const mermaidScript = `
import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
function theme() {
  return document.documentElement.dataset.theme === "light" ? "default" : "dark";
}
function render() {
  document.querySelectorAll("pre.mermaid").forEach((el) => {
    if (!el.dataset.src) el.dataset.src = el.textContent;
    el.removeAttribute("data-processed");
    el.innerHTML = el.dataset.src;
  });
  mermaid.initialize({ startOnLoad: false, theme: theme() });
  mermaid.run({ querySelector: "pre.mermaid" });
}
render();
new MutationObserver(render).observe(document.documentElement, {
  attributes: true,
  attributeFilter: ["data-theme"],
});
`;

export default defineConfig({
  site: "https://junior.mchep.dev",
  markdown: {
    remarkPlugins: [
      remarkStripTitle,
      remarkMermaid,
      [remarkRewriteLinks, { docsRoot, repoUrl, docsDir }],
    ],
  },
  integrations: [
    starlight({
      title: "Junior",
      description:
        "Hand any task to an AI junior: deterministic runbooks around one schema-validated LLM call. Built-in code review for GitLab, GitHub, and Bitbucket DC.",
      logo: { src: "./src/assets/logo.svg" },
      favicon: "/favicon.svg",
      customCss: ["./src/styles/custom.css"],
      editLink: {
        baseUrl: `${repoUrl}/edit/main/${docsDir}/`,
      },
      components: {
        EditLink: "./src/components/EditLink.astro",
      },
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/mishachepi/junior",
        },
      ],
      head: [
        {
          tag: "script",
          attrs: { type: "module" },
          content: mermaidScript,
        },
      ],
      sidebar: [
        { label: "About", link: "/" },
        { label: "Getting started", link: "/getting_started/" },
        { label: "Philosophy", link: "/philosophy/" },
        { label: "Glossary", link: "/glossary/" },
        {
          label: "Guides",
          items: [
            { label: "Use cases", link: "/use_cases/" },
            { label: "Run in CI", link: "/ci/" },
            { label: "Write a runbook in YAML", link: "/script_runbooks/" },
            { label: "Choosing a harness", link: "/agent_backends/" },
            { label: "Prompts and Context", link: "/prompts/" },
          ],
        },
        {
          label: "Reference",
          items: [
            { label: "CLI Reference", link: "/cli/" },
            { label: "Configuration", link: "/configuration/" },
            { label: "Security", link: "/prompt_injection/" },
          ],
        },
        {
          label: "Architecture",
          collapsed: true,
          items: [
            { label: "Overview", link: "/architecture/" },
            { label: "The runbook framework", link: "/architecture/runbooks/" },
            { label: "Adding a runbook", link: "/adding_runbooks/" },
            { label: "Adding a harness", link: "/adding_harnesses/" },
            {
              label: "Harness internals",
              items: [
                { label: "Claude Code", link: "/agent_backends/claudecode/" },
                { label: "Codex", link: "/agent_backends/codex/" },
                { label: "Pydantic AI", link: "/agent_backends/pydantic/" },
                { label: "DeepAgents", link: "/agent_backends/deepagents/" },
                { label: "Pi", link: "/agent_backends/pi/" },
              ],
            },
            {
              label: "Runbook example",
              items: [
                { label: "Anatomy of a run", link: "/runbook_example/readme/" },
                { label: "Review output in detail", link: "/runbook_example/output/" },
              ],
            },
          ],
        },
        { label: "FAQ", link: "/faq/" },
      ],
    }),
  ],
});
