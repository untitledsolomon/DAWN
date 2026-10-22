// Safe markdown → React.
//
// The only markdown renderer for DAWN UI. It converts a small, deliberate
// subset to React nodes and NEVER uses dangerouslySetInnerHTML, so raw text
// from web fetches / MCP results / model output cannot inject markup.
// React escapes all text children automatically; every other code path that
// used to build HTML strings and inject it (Message.tsx, ArtifactCard.tsx) now
// delegates here.
//
// Subset: paragraphs, fenced + inline code, `-` lists, `#`/`##`/`###` headings,
// **bold**, *italic*, [label](https://...) links. Links are https: only and
// always open with rel="noreferrer noopener".

import { Fragment, type ReactNode } from "react";
import MathTex from "./Math";

const HTTPS_ONLY = /^https:\/\//i;

/** Split `source` into React nodes: inline code, math, bold, italic, links, text. */
function renderInline(source: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re =
    /(`[^`]+`)|(\$\$[^$]+?\$\$)|(\$(?=[^$\s])(?:[^$\n]*\S|\S)\$(?!\d))|(\*\*[^*\n]+\*\*)|(\*[^*\n]+\*)|(\[[^\]\n]+\]\([^)\s]+\))/g;
  let last = 0;
  let key = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(source)) !== null) {
    if (m.index > last) nodes.push(<Fragment key={key++}>{source.slice(last, m.index)}</Fragment>);
    const [full, code, ddmath, inlinemath, bold, italic, link] = m;
    if (code) {
      nodes.push(<code key={key++}>{code.slice(1, -1)}</code>);
    } else if (ddmath) {
      nodes.push(
        <div key={key++} className="my-2 overflow-x-auto">
          <MathTex tex={ddmath.slice(2, -2)} display />
        </div>,
      );
    } else if (inlinemath) {
      nodes.push(<MathTex key={key++} tex={inlinemath.slice(1, -1)} display={false} />);
    } else if (bold) {
      nodes.push(<strong key={key++}>{bold.slice(2, -2)}</strong>);
    } else if (italic) {
      nodes.push(<em key={key++}>{italic.slice(1, -1)}</em>);
    } else if (link) {
      const captured = link.match(/^\[([^\]]+)\]\((.*)\)$/);
      if (captured && HTTPS_ONLY.test(captured[2])) {
        nodes.push(
          <a key={key++} href={captured[2]} target="_blank" rel="noreferrer noopener">
            {captured[1]}
          </a>,
        );
      } else {
        // Not a safe link — render the raw text, never a clickable URL.
        nodes.push(<Fragment key={key++}>{link}</Fragment>);
      }
    }
    last = m.index + full.length;
  }
  if (last < source.length) nodes.push(<Fragment key={key++}>{source.slice(last)}</Fragment>);
  return nodes;
}

function renderBlocks(text: string): ReactNode[] {
  const blocks: ReactNode[] = [];
  const lines = text.split("\n");
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Fenced code block
    const fence = line.match(/^```(\w*)\s*$/);
    if (fence) {
      const lang = fence[1];
      const buf: string[] = [];
      i += 1;
      while (i < lines.length && !/^```/.test(lines[i])) {
        buf.push(lines[i]);
        i += 1;
      }
      i += 1; // skip closing fence
      blocks.push(
        <pre key={key++}>
          <code className={lang ? `language-${lang}` : ""}>{buf.join("\n")}</code>
        </pre>,
      );
      continue;
    }

    // Heading
    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      const inner = renderInline(heading[2]);
      if (level === 1) blocks.push(<h1 key={key++}>{inner}</h1>);
      else if (level === 2) blocks.push(<h2 key={key++}>{inner}</h2>);
      else blocks.push(<h3 key={key++}>{inner}</h3>);
      i += 1;
      continue;
    }

    // Unordered list (consecutive `- ` lines)
    if (/^-\s+/.test(line)) {
      const items: ReactNode[] = [];
      while (i < lines.length && /^-\s+/.test(lines[i])) {
        items.push(<li key={key++}>{renderInline(lines[i].replace(/^-\s+/, ""))}</li>);
        i += 1;
      }
      blocks.push(<ul key={key++}>{items}</ul>);
      continue;
    }

    // Blank line
    if (!line.trim()) {
      i += 1;
      continue;
    }

    // Paragraph — gather until a blank line, fence, heading or list start
    const buf: string[] = [line];
    i += 1;
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !/^```/.test(lines[i]) &&
      !/^#{1,3}\s/.test(lines[i]) &&
      !/^-\s+/.test(lines[i])
    ) {
      buf.push(lines[i]);
      i += 1;
    }
    blocks.push(<p key={key++}>{renderInline(buf.join(" "))}</p>);
  }

  return blocks;
}

export function renderMarkdown(text: string): ReactNode {
  return <Fragment>{renderBlocks(text ?? "")}</Fragment>;
}
