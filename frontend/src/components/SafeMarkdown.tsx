import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface SafeMarkdownProps {
  content: string;
  className?: string;
}

function isSafeUrl(url?: string): boolean {
  if (!url) return false;
  const trimmed = url.trim().toLowerCase();
  // Disallow script schemes and dangerous protocols
  if (
    trimmed.startsWith('javascript:') ||
    trimmed.startsWith('vbscript:') ||
    trimmed.startsWith('data:') ||
    trimmed.startsWith('file:')
  ) {
    return false;
  }
  // Allow safe protocols or relative links
  return (
    trimmed.startsWith('http://') ||
    trimmed.startsWith('https://') ||
    trimmed.startsWith('mailto:') ||
    trimmed.startsWith('/') ||
    trimmed.startsWith('#')
  );
}

export const SafeMarkdown: React.FC<SafeMarkdownProps> = ({ content, className = '' }) => {
  return (
    <div className={`safe-markdown-root ${className}`.trim()}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Bound headings so AI output cannot dominate page typography
          h1: ({ children }) => <h3 className="markdown-heading markdown-h1">{children}</h3>,
          h2: ({ children }) => <h4 className="markdown-heading markdown-h2">{children}</h4>,
          h3: ({ children }) => <h5 className="markdown-heading markdown-h3">{children}</h5>,
          h4: ({ children }) => <h6 className="markdown-heading markdown-h4">{children}</h6>,
          h5: ({ children }) => <h6 className="markdown-heading markdown-h5">{children}</h6>,
          h6: ({ children }) => <h6 className="markdown-heading markdown-h6">{children}</h6>,

          p: ({ children }) => <p className="markdown-paragraph">{children}</p>,
          ul: ({ children }) => <ul className="markdown-list markdown-ul">{children}</ul>,
          ol: ({ children }) => <ol className="markdown-list markdown-ol">{children}</ol>,
          li: ({ children }) => <li className="markdown-list-item">{children}</li>,

          strong: ({ children }) => <strong className="markdown-strong">{children}</strong>,
          em: ({ children }) => <em className="markdown-em">{children}</em>,

          // Table support with horizontal scroll wrapper
          table: ({ children }) => (
            <div className="markdown-table-wrapper">
              <table className="markdown-table">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="markdown-thead">{children}</thead>,
          tbody: ({ children }) => <tbody className="markdown-tbody">{children}</tbody>,
          tr: ({ children }) => <tr className="markdown-tr">{children}</tr>,
          th: ({ children }) => <th className="markdown-th">{children}</th>,
          td: ({ children }) => <td className="markdown-td">{children}</td>,

          // Code blocks and inline code
          code: ({ className: codeClassName, children, ...rest }) => {
            const isInline = !codeClassName && typeof children === 'string' && !children.includes('\n');
            if (isInline) {
              return <code className="markdown-inline-code" {...rest}>{children}</code>;
            }
            return (
              <pre className="markdown-pre">
                <code className={`markdown-code-block ${codeClassName || ''}`.trim()} {...rest}>
                  {children}
                </code>
              </pre>
            );
          },

          // Safe links: validate scheme and sandbox
          a: ({ href, children }) => {
            if (isSafeUrl(href)) {
              const isExternal = href?.startsWith('http://') || href?.startsWith('https://');
              return (
                <a
                  href={href}
                  className="markdown-link"
                  target={isExternal ? '_blank' : undefined}
                  rel={isExternal ? 'noopener noreferrer' : undefined}
                >
                  {children}
                </a>
              );
            }
            return <span className="markdown-text-link">{children}</span>;
          },

          // Disallow unauthorized remote images from AI Markdown output
          img: ({ alt }) => (
            <span className="markdown-img-blocked" title="Imágenes remotas no permitidas en respuestas de texto">
              {alt ? `[Imagen: ${alt}]` : '[Imagen no disponible]'}
            </span>
          ),

          blockquote: ({ children }) => (
            <blockquote className="markdown-blockquote">{children}</blockquote>
          ),
          hr: () => <hr className="markdown-hr" />
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
};
