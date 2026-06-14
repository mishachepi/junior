import { visit } from "unist-util-visit";

/**
 * Removes the first top-level `# H1` heading from each document.
 *
 * The source markdown in ../docs keeps its H1 so the files render nicely on
 * GitHub, but Starlight already renders the frontmatter `title` as the page
 * heading. Without this we'd get two stacked titles.
 */
export default function remarkStripTitle() {
  return (tree) => {
    let removed = false;
    visit(tree, "heading", (node, index, parent) => {
      if (removed || node.depth !== 1 || !parent || index == null) return;
      parent.children.splice(index, 1);
      removed = true;
      return [visit.SKIP, index];
    });
  };
}
