'use client';

import { useState, useEffect } from 'react';
import AppShell from '@/components/layout/AppShell';
import DocumentUploadDialog from './components/DocumentUploadDialog';
import DocumentCard from './components/DocumentCard';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || '';

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export default function KnowledgePage() {
  // Document list state
  const [documents, setDocuments] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [filterTag, setFilterTag] = useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);

  // RAG search state
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [answer, setAnswer] = useState('');
  const [sources, setSources] = useState<any[]>([]);

  async function loadDocuments() {
    setLoading(true);
    try {
      const params = filterTag ? `?tags=${encodeURIComponent(filterTag)}` : '';
      const res = await fetch(`${API_BASE}/api/rag/documents${params}`);
      if (!res.ok) { setDocuments([]); return; }
      const data = await res.json();
      setDocuments(data.documents || []);
    } catch {
      setDocuments([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadDocuments(); }, [filterTag]);

  async function handleSearch() {
    if (!query.trim() || searching) return;
    setSearching(true);
    setAnswer('');
    setSources([]);
    try {
      const res = await fetch(`${API_BASE}/api/rag/query/sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, collection: 'research', top_k: 5 }),
      });
      if (!res.ok) {
        setAnswer('搜索失败，请稍后重试');
        return;
      }
      const data = await res.json();
      setAnswer(data.answer || '');
      setSources(data.sources || []);
    } catch {
      setAnswer('网络错误，请稍后重试');
    } finally {
      setSearching(false);
    }
  }

  // Collect all unique tags
  const allTags = Array.from(new Set(
    documents.flatMap((d: any) => (d.tags || '').split(',').map((t: string) => t.trim()).filter(Boolean))
  ));

  return (
    <AppShell>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
        <h1 style={{ fontSize: '20px', fontWeight: 590, color: 'var(--text-primary)', letterSpacing: '-0.3px', margin: 0 }}>
          知识库
        </h1>
        <button
          data-track="upload_document_open"
          onClick={() => setUploadOpen(true)}
          style={{
            padding: '6px 14px', fontSize: '12px', fontWeight: 510,
            background: 'var(--accent-bg)', color: '#fff',
            border: 'none', borderRadius: '6px', cursor: 'pointer',
          }}
        >
          + 上传
        </button>
      </div>

      {/* Search section */}
      <div style={{
        background: 'var(--bg-card)', border: '1px solid var(--border-subtle)',
        borderRadius: '10px', padding: '16px 20px', marginBottom: '16px',
      }}>
        <div style={{ fontSize: '12px', fontWeight: 510, color: 'var(--text-muted)', marginBottom: '10px' }}>
          搜索
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleSearch(); }}
            placeholder="搜索已上传的文档..."
            style={{
              flex: 1, padding: '8px 12px',
              background: 'var(--bg-input)', border: '1px solid var(--border-subtle)',
              borderRadius: '6px', fontSize: '13px', color: 'var(--text-primary)', outline: 'none',
            }}
          />
          <button
            data-track="knowledge_search"
            onClick={handleSearch}
            disabled={searching || !query.trim()}
            style={{
              padding: '8px 16px', fontSize: '13px', fontWeight: 510,
              background: searching || !query.trim() ? 'var(--bg-elevated)' : 'var(--accent-bg)',
              color: searching || !query.trim() ? 'var(--text-muted)' : '#fff',
              border: 'none', borderRadius: '6px', cursor: searching ? 'wait' : 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            {searching ? '搜索中...' : '搜索'}
          </button>
        </div>

        {/* Search results */}
        {(answer || sources.length > 0) && (
          <div style={{ marginTop: '14px' }}>
            {answer && (
              <div style={{
                fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.8,
                padding: '12px 14px', background: 'var(--bg-elevated)', borderRadius: '6px',
                marginBottom: sources.length > 0 ? '12px' : '0',
              }}>
                {answer}
              </div>
            )}
            {sources.length > 0 && (
              <div>
                <div style={{ fontSize: '11px', fontWeight: 510, color: 'var(--text-muted)', marginBottom: '6px' }}>
                  来源 ({sources.length})
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {sources.map((src: any, i: number) => (
                    <div key={i} style={{
                      padding: '8px 12px', background: 'var(--bg-elevated)', borderRadius: '6px',
                      borderLeft: '3px solid var(--accent)',
                    }}>
                      <div style={{ fontSize: '11px', color: 'var(--accent)', fontWeight: 510, marginBottom: '4px' }}>
                        {src.source || `Source ${i + 1}`}
                        {src.metadata?.title && <span style={{ color: 'var(--text-muted)', fontWeight: 400, marginLeft: '8px' }}>{src.metadata.title}</span>}
                      </div>
                      <div style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                        {src.text}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Tag filter */}
      {allTags.length > 0 && (
        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', marginBottom: '14px' }}>
          <button
            onClick={() => setFilterTag(null)}
            style={{
              padding: '3px 10px', fontSize: '11px', borderRadius: '10px',
              border: filterTag === null ? '1px solid var(--accent)' : '1px solid var(--border-subtle)',
              background: filterTag === null ? 'var(--accent)12' : 'transparent',
              color: filterTag === null ? 'var(--accent)' : 'var(--text-muted)',
              cursor: 'pointer', fontWeight: 510,
            }}
          >
            全部
          </button>
          {allTags.map((tag) => (
            <button
              key={tag}
              onClick={() => setFilterTag(filterTag === tag ? null : tag)}
              style={{
                padding: '3px 10px', fontSize: '11px', borderRadius: '10px',
                border: filterTag === tag ? '1px solid var(--accent)' : '1px solid var(--border-subtle)',
                background: filterTag === tag ? 'var(--accent)12' : 'transparent',
                color: filterTag === tag ? 'var(--accent)' : 'var(--text-muted)',
                cursor: 'pointer', fontWeight: 510,
              }}
            >
              {tag}
            </button>
          ))}
        </div>
      )}

      {/* Document list */}
      {loading && (
        <div style={{ fontSize: '13px', color: 'var(--text-muted)', padding: '40px 0', textAlign: 'center' }}>加载中...</div>
      )}
      {!loading && documents.length === 0 && (
        <div style={{ textAlign: 'center', padding: '60px 0' }}>
          <div style={{ fontSize: '14px', color: 'var(--text-muted)', marginBottom: '8px' }}>暂无文档</div>
          <div style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>上传研报、笔记或分析文档以构建知识库</div>
        </div>
      )}
      {!loading && documents.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {documents.map((doc: any) => (
            <DocumentCard
              key={doc.id}
              doc={doc}
              onDeleted={loadDocuments}
              onUpdated={loadDocuments}
            />
          ))}
        </div>
      )}

      {/* Upload dialog */}
      <DocumentUploadDialog
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onUploaded={loadDocuments}
      />
    </AppShell>
  );
}
