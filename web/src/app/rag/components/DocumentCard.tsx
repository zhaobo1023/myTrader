'use client';

import { useState } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || '';

interface DocumentItem {
  id: number;
  title: string;
  file_type: string;
  file_size: number;
  tags: string | null;
  memo: string | null;
  chunk_count: number;
  status: string;
  created_at: string;
  updated_at: string;
}

interface DocumentCardProps {
  doc: DocumentItem;
  onDeleted: () => void;
  onUpdated: () => void;
}

const FILE_TYPE_LABELS: Record<string, string> = {
  pdf: 'PDF', md: 'Markdown', docx: 'Word', doc: 'Word', txt: 'TXT',
};

const FILE_TYPE_COLORS: Record<string, string> = {
  pdf: '#e5534b', md: '#57ab5a', docx: '#539bf5', doc: '#539bf5', txt: 'var(--text-muted)',
};

export default function DocumentCard({ doc, onDeleted, onUpdated }: DocumentCardProps) {
  const [editing, setEditing] = useState(false);
  const [editTags, setEditTags] = useState(doc.tags || '');
  const [editMemo, setEditMemo] = useState(doc.memo || '');
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [saveError, setSaveError] = useState('');

  async function handleSave() {
    setSaving(true);
    setSaveError('');
    try {
      const res = await fetch(`${API_BASE}/api/rag/documents/${doc.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tags: editTags || null, memo: editMemo || null }),
      });
      if (res.ok) {
        setEditing(false);
        onUpdated();
      } else {
        setSaveError('保存失败，请重试');
      }
    } catch {
      setSaveError('网络错误，请重试');
    } finally { setSaving(false); }
  }

  async function handleDelete() {
    if (!confirm(`确定删除「${doc.title}」？将从知识库中移除所有相关内容。`)) return;
    setDeleting(true);
    try {
      const res = await fetch(`${API_BASE}/api/rag/documents/${doc.id}`, { method: 'DELETE' });
      if (res.ok) onDeleted();
      else alert('删除失败，请重试');
    } catch {
      alert('网络错误，请重试');
    }
    finally { setDeleting(false); }
  }

  const tagList = (doc.tags || '').split(',').map((t) => t.trim()).filter(Boolean);
  const sizeStr = doc.file_size > 1024 * 1024
    ? `${(doc.file_size / 1024 / 1024).toFixed(1)} MB`
    : `${(doc.file_size / 1024).toFixed(1)} KB`;
  const dateStr = doc.created_at?.slice(0, 16).replace('T', ' ') || '';
  const statusLabel = doc.status === 'done' ? null : (
    <span style={{
      fontSize: '10px', fontWeight: 600, padding: '1px 6px', borderRadius: '8px',
      background: doc.status === 'failed' ? 'rgba(229,83,75,0.12)' : 'rgba(187,128,9,0.12)',
      color: doc.status === 'failed' ? '#e5534b' : '#bb8009',
    }}>
      {doc.status}
    </span>
  );

  return (
    <div style={{
      background: 'var(--bg-card)', border: '1px solid var(--border-subtle)',
      borderRadius: '10px', padding: '16px 20px',
    }}>
      {/* Top row: title + actions */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <span style={{
              fontSize: '10px', fontWeight: 600, padding: '1px 6px', borderRadius: '4px',
              background: `${FILE_TYPE_COLORS[doc.file_type] || 'var(--text-muted)'}18`,
              color: FILE_TYPE_COLORS[doc.file_type] || 'var(--text-muted)',
              textTransform: 'uppercase',
            }}>
              {FILE_TYPE_LABELS[doc.file_type] || doc.file_type}
            </span>
            {statusLabel}
            <span style={{ fontSize: '14px', fontWeight: 560, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {doc.title}
            </span>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '4px', flexShrink: 0, marginLeft: '12px' }}>
          <button
            onClick={() => { if (!editing) { setEditTags(doc.tags || ''); setEditMemo(doc.memo || ''); } setEditing(!editing); }}
            style={{ fontSize: '11px', padding: '3px 8px', background: 'none', border: '1px solid var(--border-subtle)', borderRadius: '4px', color: 'var(--text-muted)', cursor: 'pointer' }}
          >
            {editing ? '取消' : '编辑'}
          </button>
          <button
            onClick={handleDelete}
            disabled={deleting}
            style={{ fontSize: '11px', padding: '3px 8px', background: 'none', border: '1px solid rgba(229,83,75,0.3)', borderRadius: '4px', color: '#e5534b', cursor: deleting ? 'wait' : 'pointer', opacity: deleting ? 0.6 : 1 }}
          >
            {deleting ? '...' : '删除'}
          </button>
        </div>
      </div>

      {/* Tags */}
      {tagList.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginBottom: '8px' }}>
          {tagList.map((t, i) => (
            <span key={i} style={{
              fontSize: '11px', padding: '1px 7px', borderRadius: '10px',
              background: 'rgba(113,112,255,0.08)', color: 'var(--accent)', fontWeight: 510,
            }}>
              {t}
            </span>
          ))}
        </div>
      )}

      {/* Memo */}
      {doc.memo && !editing && (
        <div style={{ fontSize: '12px', color: 'var(--text-muted)', lineHeight: 1.6, marginBottom: '8px', fontStyle: 'italic' }}>
          {doc.memo.length > 150 ? doc.memo.slice(0, 150) + '...' : doc.memo}
        </div>
      )}

      {/* Edit form */}
      {editing && (
        <div style={{ marginBottom: '10px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <input
            value={editTags}
            onChange={(e) => setEditTags(e.target.value)}
            placeholder="标签，用逗号分隔"
            style={{
              width: '100%', boxSizing: 'border-box', padding: '6px 8px',
              background: 'var(--bg-input)', border: '1px solid var(--border-subtle)',
              borderRadius: '4px', fontSize: '12px', color: 'var(--text-primary)', outline: 'none',
            }}
          />
          <textarea
            value={editMemo}
            onChange={(e) => setEditMemo(e.target.value)}
            placeholder="关于这篇文档的备注..."
            rows={2}
            style={{
              width: '100%', boxSizing: 'border-box', padding: '6px 8px', resize: 'vertical',
              background: 'var(--bg-input)', border: '1px solid var(--border-subtle)',
              borderRadius: '4px', fontSize: '12px', color: 'var(--text-primary)', outline: 'none',
              fontFamily: 'inherit',
            }}
          />
          <button
            onClick={handleSave}
            disabled={saving}
            style={{
              alignSelf: 'flex-end', padding: '5px 14px', fontSize: '12px', fontWeight: 510,
              background: saving ? 'var(--bg-elevated)' : 'var(--accent-bg)',
              color: saving ? 'var(--text-muted)' : '#fff',
              border: 'none', borderRadius: '5px', cursor: saving ? 'wait' : 'pointer',
            }}
          >
            {saving ? '保存中...' : '保存'}
          </button>
          {saveError && (
            <div style={{ fontSize: '11px', color: '#e5534b', marginTop: '4px' }}>{saveError}</div>
          )}
        </div>
      )}

      {/* Meta row */}
      <div style={{ display: 'flex', gap: '16px', fontSize: '11px', color: 'var(--text-muted)' }}>
        <span>{sizeStr}</span>
        <span>{doc.chunk_count} 分块</span>
        <span>{dateStr}</span>
      </div>
    </div>
  );
}
