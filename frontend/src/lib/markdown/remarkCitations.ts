import type { Plugin } from 'unified';
import type { Root, RootContent, Text } from 'mdast';
import { visit, SKIP } from 'unist-util-visit';

// Citations are emitted by the LLM as `[SOURCE_N]`, but that bracket syntax
// collides with CommonMark's shortcut/full reference links and reference
// definitions (`[label]: url`). We rewrite to an unambiguous sentinel
// `⟦SOURCE_N⟧` (U+27E6 / U+27E7) before parsing — those code points have no
// meaning in CommonMark or GFM, so the parser leaves them untouched in a
// single text node. This plugin then walks those text nodes and replaces
// each sentinel with a custom `citation` mdast node that maps to a `<cite>`
// hast element via `data.hName` / `data.hProperties`, which the renderer
// substitutes with the citation pill component.

export const CITATION_OPEN = '⟦'; // ⟦
export const CITATION_CLOSE = '⟧'; // ⟧
const CITATION_RE = /⟦SOURCE_(\d+)⟧/g;

interface CitationNode {
  type: 'citation';
  value: string;
  data: {
    hName: 'cite';
    hProperties: { dataSourceN: string };
  };
}

export const remarkCitations: Plugin<[], Root> = () => {
  return (tree) => {
    visit(tree, 'text', (node: Text, index, parent) => {
      if (!parent || index === undefined) return;
      const value = node.value;
      if (!value.includes(CITATION_OPEN)) return;

      const newChildren: RootContent[] = [];
      let cursor = 0;
      CITATION_RE.lastIndex = 0;
      let match: RegExpExecArray | null;
      while ((match = CITATION_RE.exec(value)) !== null) {
        if (match.index > cursor) {
          newChildren.push({
            type: 'text',
            value: value.slice(cursor, match.index),
          } as Text);
        }
        const citation: CitationNode = {
          type: 'citation',
          value: match[0],
          data: {
            hName: 'cite',
            hProperties: { dataSourceN: match[1] },
          },
        };
        newChildren.push(citation as unknown as RootContent);
        cursor = match.index + match[0].length;
      }
      if (cursor < value.length) {
        newChildren.push({ type: 'text', value: value.slice(cursor) } as Text);
      }

      parent.children.splice(index, 1, ...newChildren);
      return [SKIP, index + newChildren.length];
    });
  };
};
