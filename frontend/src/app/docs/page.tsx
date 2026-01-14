'use client';

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import Link from 'next/link';
import ReactMarkdown, { Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { 
  ArrowLeft, Book, Code, Users, 
  Layers, Container, TestTube, Settings,
  Loader2, ExternalLink, ChevronRight, ChevronDown,
  Menu, X, Hash
} from 'lucide-react';

interface DocMeta {
  id: string;
  filename: string;
}

interface Heading {
  id: string;
  text: string;
  level: number;
}

const DOC_CONFIG: Record<string, { label: string; icon: React.ElementType }> = {
  'user-guide': { label: 'User Guide', icon: Users },
  'architecture': { label: 'Architecture', icon: Layers },
  'developer-guide': { label: 'Developer Guide', icon: Code },
  'development-environment': { label: 'Dev Environment', icon: Container },
  'testing': { label: 'Testing', icon: TestTube },
  'adding-components': { label: 'Adding Components', icon: Settings },
};

// Generate slug from heading text
function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .trim();
}

// Extract only h2 (##) headings from markdown content for navigation
function extractHeadings(markdown: string): Heading[] {
  const headingRegex = /^##\s+(.+)$/gm;
  const headings: Heading[] = [];
  let match;
  
  while ((match = headingRegex.exec(markdown)) !== null) {
    const text = match[1].trim();
    // Skip code-like headings
    if (!text.startsWith('`')) {
      headings.push({
        id: slugify(text),
        text,
        level: 2,
      });
    }
  }
  
  return headings;
}

export default function DocsPage() {
  const [docs, setDocs] = useState<DocMeta[]>([]);
  const [activeDoc, setActiveDoc] = useState<string>('user-guide');
  const [content, setContent] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [activeHeading, setActiveHeading] = useState<string>('');
  const [expandedDocs, setExpandedDocs] = useState<Set<string>>(new Set(['user-guide']));
  const [sidebarOpen, setSidebarOpen] = useState(false);
  
  // Ref to prevent scroll spy during programmatic scrolling
  const isScrollingRef = useRef(false);

  // Extract headings from current content
  const headings = useMemo(() => extractHeadings(content), [content]);

  // Add docs-page class to body for Safari optimization
  useEffect(() => {
    document.body.classList.add('docs-page');
    return () => {
      document.body.classList.remove('docs-page');
    };
  }, []);

  // Fetch available docs
  useEffect(() => {
    fetch('/api/docs')
      .then(res => res.json())
      .then(data => {
        setDocs(data.docs || []);
        if (data.docs?.length && !data.docs.find((d: DocMeta) => d.id === 'user-guide')) {
          setActiveDoc(data.docs[0].id);
        }
      })
      .catch(console.error);
  }, []);

  // Cache for doc content to avoid flashing on navigation
  const contentCache = useRef<Record<string, string>>({});

  // Fetch doc content when activeDoc changes
  useEffect(() => {
    if (!activeDoc) return;
    
    // Check cache first
    if (contentCache.current[activeDoc]) {
      setContent(contentCache.current[activeDoc]);
      setExpandedDocs(prev => new Set([...prev, activeDoc]));
      setActiveHeading('');
      window.scrollTo({ top: 0, behavior: 'instant' });
      return;
    }
    
    setLoading(true);
    fetch(`/api/docs/${activeDoc}`)
      .then(res => res.json())
      .then(data => {
        const docContent = data.content || '';
        contentCache.current[activeDoc] = docContent;
        setContent(docContent);
        setLoading(false);
        setExpandedDocs(prev => new Set([...prev, activeDoc]));
        setActiveHeading('');
        window.scrollTo({ top: 0, behavior: 'instant' });
      })
      .catch(err => {
        console.error(err);
        setContent('# Error\n\nFailed to load documentation.');
        setLoading(false);
      });
  }, [activeDoc]);

  // Scroll spy - track which heading is currently in view
  useEffect(() => {
    if (headings.length === 0) return;

    const handleScroll = () => {
      // Skip during programmatic scrolling
      if (isScrollingRef.current) return;
      
      // Find all heading elements
      const headingElements = headings
        .map(h => ({ id: h.id, element: document.getElementById(h.id) }))
        .filter(h => h.element !== null);

      if (headingElements.length === 0) return;

      // Find the heading closest to the top of the viewport (with some offset for header)
      const scrollTop = window.scrollY;
      const headerOffset = 100; // Account for fixed header

      let activeId = headingElements[0].id;
      
      for (const { id, element } of headingElements) {
        if (element) {
          const rect = element.getBoundingClientRect();
          const elementTop = rect.top + scrollTop;
          
          // If this heading is above the viewport + offset, it's potentially active
          if (elementTop <= scrollTop + headerOffset) {
            activeId = id;
          } else {
            // We've passed the scroll position, break
            break;
          }
        }
      }

      setActiveHeading(activeId);
    };

    // Initial check after content renders
    const timeoutId = setTimeout(handleScroll, 200);
    
    // Listen to scroll events
    window.addEventListener('scroll', handleScroll, { passive: true });

    return () => {
      clearTimeout(timeoutId);
      window.removeEventListener('scroll', handleScroll);
    };
  }, [headings]);

  // Scroll to element with offset for fixed header
  const scrollToElement = useCallback((elementId: string) => {
    const element = document.getElementById(elementId);
    if (element) {
      // Prevent scroll spy from overriding during programmatic scroll
      isScrollingRef.current = true;
      
      const headerOffset = 80;
      const elementPosition = element.getBoundingClientRect().top + window.scrollY;
      const offsetPosition = elementPosition - headerOffset;
      
      window.scrollTo({
        top: offsetPosition,
        behavior: 'smooth'
      });
      
      // Re-enable scroll spy after scroll animation completes
      setTimeout(() => {
        isScrollingRef.current = false;
      }, 500);
    }
  }, []);

  // Handle link clicks
  const handleLinkClick = useCallback((href: string, e: React.MouseEvent) => {
    // Anchor link - scroll to element
    if (href.startsWith('#')) {
      e.preventDefault();
      const id = href.slice(1);
      scrollToElement(id);
      setSidebarOpen(false);
      return;
    }

    // Internal doc link (*.md)
    const mdMatch = href.match(/^([a-z-]+)\.md(?:#(.+))?$/);
    if (mdMatch) {
      e.preventDefault();
      const [, docId, anchor] = mdMatch;
      if (docs.find(d => d.id === docId)) {
        setActiveDoc(docId);
        if (anchor) {
          setTimeout(() => {
            scrollToElement(anchor);
          }, 300);
        }
      }
      setSidebarOpen(false);
      return;
    }
  }, [docs, scrollToElement]);

  // Sort docs according to DOC_CONFIG order
  const sortedDocs = [...docs].sort((a, b) => {
    const keys = Object.keys(DOC_CONFIG);
    const aIdx = keys.indexOf(a.id);
    const bIdx = keys.indexOf(b.id);
    return (aIdx === -1 ? 999 : aIdx) - (bIdx === -1 ? 999 : bIdx);
  });

  // Toggle doc expansion
  const toggleExpanded = useCallback((docId: string) => {
    setExpandedDocs(prev => {
      const next = new Set(prev);
      if (next.has(docId)) {
        next.delete(docId);
      } else {
        next.add(docId);
      }
      return next;
    });
  }, []);

  // Handle doc click
  const handleDocClick = useCallback((docId: string) => {
    setActiveDoc(docId);
    setSidebarOpen(false);
  }, []);

  // Handle heading click
  const handleHeadingClick = useCallback((headingId: string) => {
    // Immediately set active heading for responsive UI
    setActiveHeading(headingId);
    scrollToElement(headingId);
    setSidebarOpen(false);
  }, [scrollToElement]);

  // Helper to extract text from React children
  const getTextFromChildren = (children: React.ReactNode): string => {
    if (typeof children === 'string') return children;
    if (typeof children === 'number') return String(children);
    if (Array.isArray(children)) {
      return children.map(getTextFromChildren).join('');
    }
    if (children && typeof children === 'object' && 'props' in children) {
      const element = children as { props?: { children?: React.ReactNode } };
      return getTextFromChildren(element.props?.children);
    }
    return '';
  };

  // Custom components for ReactMarkdown
  const components: Components = {
    a: ({ href, children }) => {
      const url = href || '';
      
      if (url.startsWith('http://') || url.startsWith('https://')) {
        return (
          <a 
            href={url} 
            target="_blank" 
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1"
          >
            {children}
            <ExternalLink className="w-3 h-3 inline" />
          </a>
        );
      }

      return (
        <a 
          href={url}
          onClick={(e) => handleLinkClick(url, e)}
          className="cursor-pointer"
        >
          {children}
        </a>
      );
    },
    h1: ({ children }) => {
      const text = getTextFromChildren(children);
      const id = slugify(text);
      return <h1 id={id} className="group">{children}</h1>;
    },
    h2: ({ children }) => {
      const text = getTextFromChildren(children);
      const id = slugify(text);
      return (
        <h2 id={id} className="group flex items-center gap-2">
          {children}
          <a href={`#${id}`} className="opacity-0 group-hover:opacity-100 transition-opacity">
            <Hash className="w-4 h-4 text-muted" />
          </a>
        </h2>
      );
    },
    h3: ({ children }) => {
      const text = getTextFromChildren(children);
      const id = slugify(text);
      return (
        <h3 id={id} className="group flex items-center gap-2">
          {children}
          <a href={`#${id}`} className="opacity-0 group-hover:opacity-100 transition-opacity">
            <Hash className="w-4 h-4 text-muted" />
          </a>
        </h3>
      );
    },
    h4: ({ children }) => {
      const text = getTextFromChildren(children);
      const id = slugify(text);
      return <h4 id={id}>{children}</h4>;
    },
    pre: ({ children }) => (
      <pre className="overflow-x-auto">{children}</pre>
    ),
    code: ({ className, children }) => {
      const isInline = !className;
      if (isInline) {
        return <code className="text-green bg-base px-1.5 py-0.5 rounded text-sm">{children}</code>;
      }
      return <code className={className}>{children}</code>;
    },
    table: ({ children }) => (
      <div className="overflow-x-auto">
        <table>{children}</table>
      </div>
    ),
  };

  // Sidebar content - memoized to prevent re-renders
  const sidebarContent = useMemo(() => (
    <nav className="space-y-1">
      {sortedDocs.map((doc) => {
        const config = DOC_CONFIG[doc.id] || { label: doc.id, icon: Book };
        const Icon = config.icon;
        const isActive = activeDoc === doc.id;
        const isExpanded = expandedDocs.has(doc.id);
        const docHeadings = isActive ? headings : [];

        return (
          <div key={doc.id} className="select-none">
            {/* Doc title row */}
            <div 
              className={`flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors duration-200 ${
                isActive 
                  ? 'bg-lavender/10 text-lavender' 
                  : 'text-subtext hover:text-text hover:bg-surface'
              }`}
            >
              {/* Expand/Collapse button */}
              <button
                onClick={() => toggleExpanded(doc.id)}
                className="p-0.5 hover:bg-overlay/50 rounded transition-colors"
              >
                {isExpanded ? (
                  <ChevronDown className="w-4 h-4" />
                ) : (
                  <ChevronRight className="w-4 h-4" />
                )}
              </button>
              
              {/* Doc link */}
              <button
                onClick={() => handleDocClick(doc.id)}
                className="flex items-center gap-2 flex-1 text-left"
              >
                <Icon className="w-4 h-4 flex-shrink-0" />
                <span className="text-sm font-medium truncate">{config.label}</span>
              </button>
            </div>

            {/* Headings tree (only for active doc) */}
            {isExpanded && docHeadings.length > 0 && (
              <div className="ml-5 pl-3 border-l border-overlay/50 space-y-0.5 py-1">
                {docHeadings.map((heading) => (
                  <button
                    key={heading.id}
                    onClick={() => handleHeadingClick(heading.id)}
                    className={`w-full text-left py-1 px-2 text-xs rounded truncate transition-colors duration-150 ${
                      activeHeading === heading.id
                        ? 'text-lavender bg-lavender/10'
                        : 'text-muted hover:text-subtext hover:bg-surface/50'
                    }`}
                  >
                    {heading.text}
                  </button>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </nav>
  ), [sortedDocs, activeDoc, expandedDocs, headings, activeHeading, toggleExpanded, handleDocClick, handleHeadingClick]);

  return (
    <div className="min-h-screen bg-base">
      {/* Header */}
      <header className="fixed top-0 left-0 right-0 z-50 bg-base border-b border-overlay/30">
        <div className="flex items-center justify-between h-14 px-4">
          <div className="flex items-center gap-4">
            {/* Mobile menu button */}
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="lg:hidden p-2 text-subtext hover:text-text rounded-lg hover:bg-surface transition-colors"
            >
              {sidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
            
            <Link 
              href="/"
              className="flex items-center gap-2 text-subtext hover:text-text transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              <span className="hidden sm:inline">Back</span>
            </Link>
            <div className="h-5 w-px bg-overlay hidden sm:block" />
            <div className="flex items-center gap-2">
              <Book className="w-5 h-5 text-lavender" />
              <span className="font-semibold text-text">Documentation</span>
            </div>
          </div>
          
          {/* Current section indicator */}
          <div className="hidden md:flex items-center gap-2 text-sm text-muted">
            <span>{DOC_CONFIG[activeDoc]?.label || activeDoc}</span>
            {activeHeading && (
              <>
                <ChevronRight className="w-4 h-4" />
                <span className="text-subtext truncate max-w-[200px]">
                  {headings.find(h => h.id === activeHeading)?.text}
                </span>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-base/90 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Mobile sidebar */}
      {sidebarOpen && (
        <aside className="fixed top-14 left-0 bottom-0 w-72 z-40 bg-base border-r border-overlay/30 overflow-y-auto lg:hidden">
          <div className="p-4">
            {sidebarContent}
          </div>
        </aside>
      )}

      {/* Desktop layout */}
      <div className="flex pt-14">
        {/* Desktop sidebar */}
        <aside className="hidden lg:block fixed top-14 left-0 bottom-0 w-64 border-r border-overlay/30 overflow-y-auto">
          <div className="p-4">
            {sidebarContent}
          </div>
        </aside>

        {/* Main content */}
        <main className="flex-1 lg:ml-64 min-h-[calc(100vh-3.5rem)]">
          <div className="max-w-4xl mx-auto px-6 py-8">
            <div className="bg-surface/50 border border-overlay/50 rounded-xl p-6 md:p-8">
              {loading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="w-8 h-8 text-lavender animate-spin" />
                </div>
              ) : (
                <article className="prose prose-invert max-w-none 
                  prose-headings:text-text prose-headings:scroll-mt-20
                  prose-h1:text-2xl prose-h1:font-bold prose-h1:mb-6 prose-h1:pb-4 prose-h1:border-b prose-h1:border-overlay/50
                  prose-h2:text-xl prose-h2:font-semibold prose-h2:mt-10 prose-h2:mb-4
                  prose-h3:text-lg prose-h3:font-medium prose-h3:mt-8 prose-h3:mb-3
                  prose-p:text-subtext prose-p:leading-relaxed
                  prose-li:text-subtext 
                  prose-strong:text-text 
                  prose-pre:bg-base prose-pre:border prose-pre:border-overlay/50 prose-pre:rounded-lg
                  prose-a:text-lavender hover:prose-a:text-mauve prose-a:no-underline hover:prose-a:underline
                  prose-table:text-subtext 
                  prose-th:text-text prose-th:border-overlay prose-th:bg-base/50
                  prose-td:border-overlay/50
                  prose-hr:border-overlay/50
                  prose-blockquote:border-lavender/50 prose-blockquote:bg-lavender/5 prose-blockquote:rounded-r-lg">
                  <ReactMarkdown 
                    remarkPlugins={[remarkGfm]}
                    components={components}
                  >
                    {content}
                  </ReactMarkdown>
                </article>
              )}
            </div>

            {/* Footer navigation */}
            <div className="flex justify-between items-center mt-8 pt-6 border-t border-overlay/30">
              {(() => {
                const currentIdx = sortedDocs.findIndex(d => d.id === activeDoc);
                const prevDoc = sortedDocs[currentIdx - 1];
                const nextDoc = sortedDocs[currentIdx + 1];
                
                return (
                  <>
                    {prevDoc ? (
                      <button
                        onClick={() => handleDocClick(prevDoc.id)}
                        className="flex items-center gap-2 text-subtext hover:text-lavender transition-colors group"
                      >
                        <ArrowLeft className="w-4 h-4 group-hover:-translate-x-1 transition-transform" />
                        <span className="text-sm">{DOC_CONFIG[prevDoc.id]?.label || prevDoc.id}</span>
                      </button>
                    ) : <div />}
                    
                    {nextDoc ? (
                      <button
                        onClick={() => handleDocClick(nextDoc.id)}
                        className="flex items-center gap-2 text-subtext hover:text-lavender transition-colors group"
                      >
                        <span className="text-sm">{DOC_CONFIG[nextDoc.id]?.label || nextDoc.id}</span>
                        <ArrowLeft className="w-4 h-4 rotate-180 group-hover:translate-x-1 transition-transform" />
                      </button>
                    ) : <div />}
                  </>
                );
              })()}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
