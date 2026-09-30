import { type ReactNode } from "react";

/** Markdown [label](https://...) or bare http(s) URL; bare URLs drop common trailing punctuation. */
const TOKEN =
  /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|(https?:\/\/[^\s<>"'）\]\uFF09]+)/g;

const TRAILING_PUNCT = /[),.，。；;:：]+$/;

function splitBareUrl(raw: string): { href: string; trailing: string } {
  const m = raw.match(TRAILING_PUNCT);
  if (!m) return { href: raw, trailing: "" };
  return { href: raw.slice(0, -m[0].length), trailing: m[0] };
}

/** Turn report markdown text into nodes with clickable http(s) links; keep other text verbatim. */
export function linkifyReport(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let last = 0;
  let key = 0;
  const re = new RegExp(TOKEN.source, "g");
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) {
      nodes.push(text.slice(last, m.index));
    }
    if (m[1] !== undefined && m[2] !== undefined) {
      nodes.push(
        <a key={key++} href={m[2]} target="_blank" rel="noopener">
          {m[1]}
        </a>,
      );
    } else {
      const { href, trailing } = splitBareUrl(m[3]);
      if (href) {
        nodes.push(
          <a key={key++} href={href} target="_blank" rel="noopener">
            {href}
          </a>,
        );
      }
      if (trailing) nodes.push(trailing);
    }
    last = re.lastIndex;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}
