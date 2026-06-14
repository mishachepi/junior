import { visit } from "unist-util-visit";

const escape = (s) =>
  s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

/**
 * Turns ```mermaid fenced blocks into `<pre class="mermaid">` so they bypass
 * the syntax highlighter and get rendered client-side by mermaid.js.
 */
export default function remarkMermaid() {
  return (tree) => {
    visit(tree, "code", (node) => {
      if (node.lang !== "mermaid") return;
      node.type = "html";
      node.value = `<pre class="mermaid">${escape(node.value)}</pre>`;
    });
  };
}
