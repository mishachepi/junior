import path from "node:path";
import { visit } from "unist-util-visit";

/**
 * Rewrites internal links in the docs so they work on the published site.
 *
 * Source files in ../docs cross-link with relative paths (so they also work
 * when browsed on GitHub). On the site:
 *   - `*.md` links become extensionless, lowercased Starlight routes, e.g.
 *     `agent_backends/pydantic.md` -> `/agent_backends/pydantic/` and
 *     `faq.md#anchor` -> `/faq/#anchor`.
 *   - links that resolve under `examples/` (excluded from the site — those are
 *     copy-paste reference prompts/configs) point at the GitHub repo instead.
 *
 * @param {{ docsRoot: string, repoUrl: string, docsDir?: string }} options
 *   docsRoot: absolute path to the docs/ source dir;
 *   repoUrl:  base GitHub repo URL (no trailing slash);
 *   docsDir:  docs path within the repo (default "docs").
 */
export default function remarkRewriteLinks({ docsRoot, repoUrl, docsDir = "docs" } = {}) {
  return (tree, file) => {
    const fileAbs = file.path ?? file.history?.[0];
    if (!fileAbs || !docsRoot) return;
    const relDir = path.posix.dirname(
      path.relative(docsRoot, fileAbs).split(path.sep).join("/")
    );

    visit(tree, "link", (node) => {
      const url = node.url;
      if (!url || /^(https?:)?\/\//.test(url) || url.startsWith("mailto:") || url.startsWith("#")) {
        return;
      }

      const [target, hash] = url.split("#");
      const isDir = target.endsWith("/");
      const resolved = path.posix.normalize(path.posix.join(relDir, target));

      // Links into examples/ leave the site → send readers to the repo.
      if (resolved === "examples" || resolved.startsWith("examples/")) {
        const kind = isDir ? "tree" : "blob";
        node.url = `${repoUrl}/${kind}/main/${docsDir}/${resolved}`;
        return;
      }

      if (!target.endsWith(".md")) return;

      const slug = resolved.replace(/\.md$/, "").toLowerCase().replace(/(^|\/)index$/, "$1");
      const clean = slug.replace(/^\.?\/?/, "").replace(/\/$/, "");
      node.url = `/${clean}${clean ? "/" : ""}${hash ? `#${hash}` : ""}`;
    });
  };
}
