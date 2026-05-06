import type { Plugin } from 'unified';
import type { Root, RootContent, Text } from 'mdast';
import { visit } from 'unist-util-visit';

// AST-aware citation handling for `[SOURCE_N]` markers emitted by the LLM.
//
// Why the work happens here, not on the source string:
//   - We only ever process `text` mdast nodes, so content inside `code`,
//     `inlineCode`, `html`, `yaml`, `math`, and `inlineMath` nodes is left
//     completely untouched. Source-string regex can't tell those apart.
//   - The mdast parser preserves `[SOURCE_…]` patterns (and even sloppy
//     unclosed chains) as single contiguous `text` nodes — verified against
//     remark-parse output for the patterns we observe in production. That
//     means a single regex pass per text node is enough; we don't have to
//     worry about a citation being split across two nodes by markdown rules.
//   - This eliminates the previous source-level pipeline entirely (sentinel
//     substitution, sloppy-list canonicalization, trailing-partial trim),
//     which had to be careful about not mangling code blocks.
//
// What we recognize:
//   - Canonical:     [SOURCE_3]                     → 1 citation
//   - Adjacent list: [SOURCE_1][SOURCE_2]           → 2 citations
//   - Sloppy lists the LLM keeps producing despite the system prompt:
//                    [SOURCE_1, SOURCE_2, SOURCE_3] → 3 citations
//                    [SOURCE_1, [SOURCE_2, [SOURCE_3]
//                    [SOURCE_1,SOURCE_2]
//                    [SOURCE_1, 2, 3]
//                    [SOURCE_1; SOURCE_2]
//   - Streaming partials at the trailing edge of the message — either hidden
//     until they close (during streaming) or best-effort recovered (after).

interface RemarkCitationsOptions {
  /**
   * When true, an unclosed `[SOURCE_…` chain at the very end of the document
   * is hidden from the rendered output until its closing bracket arrives.
   * When false, the same fragment is best-effort closed and rendered as
   * adjacent canonical citations (recovers from LLMs that forget the `]`).
   */
  isStreaming?: boolean;
}

const SLOPPY_LIST = /\[SOURCE_\d+(?:\s*[,;]\s*\[?(?:SOURCE_)?\d+)+\s*\]/g;
const CANONICAL = /\[SOURCE_(\d+)\]/g;

// An "element" prefix at any point in a citation chain: an optional `[`,
// optional partial letter run (`S`, `SO`, …, `SOURCE_`), optional partial
// digit run. Every component is optional so the regex matches in-flight
// fragments at every keystroke during streaming.
const ELEMENT = `\\[?(?:S(?:O(?:U(?:R(?:C(?:E(?:_\\d*)?)?)?)?)?)?)?`;
// The full trailing-partial chain: a required leading `[` (this is the
// citation's open bracket), followed by an in-flight first element, followed
// by zero or more `,`/`;`-separated subsequent elements, anchored to end of
// the buffer. Catches every step of:
//   [, [S, …, [SOURCE_1, [SOURCE_1,, [SOURCE_1, [, [SOURCE_1, [SOU,
//   [SOURCE_1, [SOURCE_2, …
const TRAILING_PARTIAL = new RegExp(
  `\\[(?:S(?:O(?:U(?:R(?:C(?:E(?:_\\d*)?)?)?)?)?)?)?` +
    `(?:\\s*[,;]\\s*${ELEMENT})*` +
    `$`
);

// Fix two additional malformed patterns the LLM emits:
//   1. [SOURCE_NText  — open bracket, digits, then prose without a closing ]
//   2. SOURCE_N       — completely naked, no brackets at all
// Both are normalised to [SOURCE_N] so the canonical pass can pick them up.
function normalizeMalformedCitations(value: string): string {
  // Fix fused-bracket form: [SOURCE_3Foo → [SOURCE_3]Foo
  // Lookahead asserts the char after the digits is NOT ], ,, ;, whitespace, digit, or [
  // (i.e. it must be the start of prose that the LLM glued on without closing the bracket).
  value = value.replace(/\[SOURCE_(\d+)(?=[^\],;\s\d[])/g, '[SOURCE_$1]');
  // Fix naked form: SOURCE_3 → [SOURCE_3]
  // Lookbehind ensures we don't double-wrap already-bracketed [SOURCE_N].
  // Lookahead ensures we don't double-wrap trailing ] (SOURCE_3] edge case).
  value = value.replace(/(?<!\[)SOURCE_(\d+)(?!\])/g, '[SOURCE_$1]');
  return value;
}

function expandIds(text: string): string {
  const ids = text.match(/\d+/g) ?? [];
  return ids.map((id) => `[SOURCE_${id}]`).join('');
}

function canonicalizeSloppyLists(value: string): string {
  return value.replace(SLOPPY_LIST, expandIds);
}

function buildCitationNode(idx: string): RootContent {
  return {
    type: 'citation',
    value: `[SOURCE_${idx}]`,
    data: {
      hName: 'cite',
      hProperties: { dataSourceN: idx },
    },
  } as unknown as RootContent;
}

function expandCanonicalToNodes(value: string): RootContent[] | null {
  CANONICAL.lastIndex = 0;
  const matches: RegExpExecArray[] = [];
  let m: RegExpExecArray | null;
  while ((m = CANONICAL.exec(value)) !== null) matches.push(m);
  if (matches.length === 0) return null;

  const out: RootContent[] = [];
  let cursor = 0;
  for (const match of matches) {
    if (match.index > cursor) {
      out.push({ type: 'text', value: value.slice(cursor, match.index) } as Text);
    }
    out.push(buildCitationNode(match[1]));
    cursor = match.index + match[0].length;
  }
  if (cursor < value.length) {
    out.push({ type: 'text', value: value.slice(cursor) } as Text);
  }
  return out;
}

export const remarkCitations: Plugin<[RemarkCitationsOptions?], Root> = (
  options = {}
) => {
  const isStreaming = options.isStreaming ?? false;

  return (tree) => {
    // Pass 1: find the last text node in document order. Pre-order DFS visits
    // text leaves in the order they appear, so the last one assigned is the
    // trailing text of the message. We only apply trailing-partial logic to
    // this node — partials only appear at the document's tail during a stream.
    let lastTextNode: Text | null = null;
    visit(tree, 'text', (node: Text) => {
      lastTextNode = node;
    });

    // Pass 2: canonicalize, partial-handle, and expand into citation nodes.
    // unist-util-visit skips into `code` / `inlineCode` / `html` / `yaml` /
    // `math` / `inlineMath` because they're leaf nodes (value-bearing, no
    // children), so this walk is implicitly code-aware.
    visit(tree, 'text', (node: Text, index, parent) => {
      if (!parent || index === undefined) return;

      let value = normalizeMalformedCitations(canonicalizeSloppyLists(node.value));

      if (node === lastTextNode) {
        if (isStreaming) {
          value = value.replace(TRAILING_PARTIAL, '');
        } else {
          value = value.replace(TRAILING_PARTIAL, (match) => {
            const ids = match.match(/\d+/g) ?? [];
            return ids.length === 0 ? '' : expandIds(match);
          });
        }
      }

      const expanded = expandCanonicalToNodes(value);
      if (!expanded) {
        if (value !== node.value) node.value = value;
        return;
      }

      parent.children.splice(index, 1, ...expanded);
      // Skip past the inserted nodes so we don't re-enter them.
      return ['skip', index + expanded.length];
    });
  };
};
