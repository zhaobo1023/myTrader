'use client';

import { useState, useRef, useCallback } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || '';

interface DocumentUploadDialogProps {
  open: boolean;
  onClose: () => void;
  onUploaded: () => void;
}

export default function DocumentUploadDialog({ open, onClose, onUploaded }: DocumentUploadDialogProps) {
  const [title, setTitle] = useState('');
  const [tags, setTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState('');
  const [memo, setMemo] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const ACCEPTED = '.pdf,.md,.markdown,.docx,.doc,.txt';

  function reset() {
    setTitle(''); setTags([]); setTagInput(''); setMemo('');
    setFile(null); setError('');
  }

  function handleClose() {
    if (uploading) return;
    reset();
    onClose();
  }

  function addTag(val: string) {
    const t = val.trim();
    if (t && !tags.includes(t)) setTags([...tags, t]);
    setTagInput('');
  }

  function removeTag(idx: number) {
    setTags(tags.filter((_, i) => i !== idx));
  }

  function handleFileSelect(f: File) {
    const ext = '.' + f.name.split('.').pop()?.toLowerCase();
    if (!ACCEPTED.split(',').includes(ext)) {
      setError('Unsupported file type. Allowed: PDF, Markdown, Word, TXT');
      return;
    }
    setFile(f);
    if (!title) setTitle(f.name.replace(/\.[^.]+$/, ''));
    setError('');
  }

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files[0]) handleFileSelect(e.dataTransfer.files[0]);
  }, [tags, title]);

  async function handleUpload() {
    if (!file || uploading) return;
    setUploading(true);
    setError('');

    const formData = new FormData();
    formData.append('file', file);
    if (title.trim()) formData.append('title', title.trim());
    if (tags.length > 0) formData.append('tags', tags.join(','));
    if (memo.trim()) formData.append('memo', memo.trim());

    try {
      const res = await fetch(`${API_BASE}/api/rag/documents/upload`, {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail || 'Upload failed');
      } else {
        handleClose();
        onUploaded();
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setUploading(false);
    }
  }

  if (!open) return null;

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'rgba(0,0,0,0.45)',
      }}
      onClick={handleClose}
    >
      <div
        style={{
          background: 'var(--bg-panel)', border: '1px solid var(--border-subtle)',
          borderRadius: '12px', padding: '24px', width: '460px', maxWidth: '95vw',
          boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <div style={{ fontSize: '15px', fontWeight: 590, color: 'var(--text-primary)' }}>Upload Document</div>
          <button onClick={handleClose} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: '18px', cursor: 'pointer', lineHeight: 1 }}>&times;</button>
        </div>

        {/* Drop zone */}
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
          style={{
            border: `2px dashed ${dragOver ? 'var(--accent)' : 'var(--border-subtle)'}`,
            borderRadius: '8px', padding: '28px 20px', textAlign: 'center',
            cursor: 'pointer', marginBottom: '16px',
            background: dragOver ? 'rgba(113,112,255,0.06)' : 'transparent',
            transition: 'all 0.15s',
          }}
        >
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPTED}
            style={{ display: 'none' }}
            onChange={(e) => { if (e.target.files?.[0]) handleFileSelect(e.target.files[0]); }}
          />
          {file ? (
            <div>
              <div style={{ fontSize: '13px', color: 'var(--text-primary)', fontWeight: 510 }}>{file.name}</div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                {(file.size / 1024).toFixed(1)} KB
              </div>
            </div>
          ) : (
            <div>
              <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '4px' }}>
                Drag & drop or click to upload
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                PDF / Markdown / Word / TXT
              </div>
            </div>
          )}
        </div>

        {/* Title */}
        <div style={{ marginBottom: '14px' }}>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '5px' }}>Title</div>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Document title"
            style={{
              width: '100%', boxSizing: 'border-box', padding: '7px 10px',
              background: 'var(--bg-input)', border: '1px solid var(--border-subtle)',
              borderRadius: '5px', fontSize: '13px', color: 'var(--text-primary)', outline: 'none',
            }}
          />
        </div>

        {/* Tags */}
        <div style={{ marginBottom: '14px' }}>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '5px' }}>Tags (press Enter to add)</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px', marginBottom: '5px' }}>
            {tags.map((t, i) => (
              <span key={i} style={{
                display: 'inline-flex', alignItems: 'center', gap: '4px',
                padding: '2px 8px', borderRadius: '10px', fontSize: '11px', fontWeight: 520,
                background: 'rgba(113,112,255,0.1)', color: 'var(--accent)',
              }}>
                {t}
                <button
                  onClick={() => removeTag(i)}
                  style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '13px', lineHeight: 1, padding: 0 }}
                >&times;</button>
              </span>
            ))}
          </div>
          <input
            value={tagInput}
            onChange={(e) => setTagInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addTag(tagInput); } }}
            placeholder="e.g. sentiment, monthly, fund-manager"
            style={{
              width: '100%', boxSizing: 'border-box', padding: '7px 10px',
              background: 'var(--bg-input)', border: '1px solid var(--border-subtle)',
              borderRadius: '5px', fontSize: '12px', color: 'var(--text-primary)', outline: 'none',
            }}
          />
        </div>

        {/* Memo */}
        <div style={{ marginBottom: '18px' }}>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '5px' }}>Notes</div>
          <textarea
            value={memo}
            onChange={(e) => setMemo(e.target.value)}
            placeholder="Why is this document valuable? How do you plan to use it?"
            rows={3}
            style={{
              width: '100%', boxSizing: 'border-box', padding: '7px 10px', resize: 'vertical',
              background: 'var(--bg-input)', border: '1px solid var(--border-subtle)',
              borderRadius: '5px', fontSize: '12px', color: 'var(--text-primary)', outline: 'none',
              fontFamily: 'inherit', lineHeight: 1.6,
            }}
          />
        </div>

        {/* Error */}
        {error && (
          <div style={{ padding: '7px 10px', background: 'rgba(229,83,75,0.08)', border: '1px solid rgba(229,83,75,0.2)', borderRadius: '5px', fontSize: '12px', color: '#e5534b', marginBottom: '12px' }}>
            {error}
          </div>
        )}

        {/* Actions */}
        <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
          <button
            onClick={handleClose}
            disabled={uploading}
            style={{
              padding: '7px 16px', fontSize: '13px',
              background: 'none', border: '1px solid var(--border-subtle)',
              borderRadius: '6px', color: 'var(--text-secondary)', cursor: uploading ? 'wait' : 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleUpload}
            disabled={!file || uploading}
            style={{
              padding: '7px 20px', fontSize: '13px', fontWeight: 510,
              background: !file || uploading ? 'var(--bg-elevated)' : 'var(--accent-bg)',
              color: !file || uploading ? 'var(--text-muted)' : '#fff',
              border: 'none', borderRadius: '6px', cursor: !file || uploading ? 'not-allowed' : 'pointer',
            }}
          >
            {uploading ? 'Parsing & Embedding...' : 'Upload'}
          </button>
        </div>
      </div>
    </div>
  );
}
