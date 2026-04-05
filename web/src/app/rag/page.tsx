'use client';

import { useState, useEffect } from 'react';
import Navbar from '@/components/layout/Navbar';
import { useAuthStore } from '@/lib/store';
import { useRouter } from 'next/navigation';

export default function RAGPage() {
  const router = useRouter();
  const { user } = useAuthStore();
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState<Array<{ role: string; content: string }>>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!user) router.push('/login');
  }, [user, router]);

  const handleQuery = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || loading) return;

    const userMessage = query.trim();
    setQuery('');
    setMessages((prev) => [...prev, { role: 'user', content: userMessage }]);
    setLoading(true);

    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/rag/query`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ query: userMessage }),
        },
      );

      if (!response.ok) throw new Error('RAG query failed');

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let fullAnswer = '';

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const text = decoder.decode(value, { stream: true });
          for (const line of text.split('\n')) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));
                if (data.type === 'token' && data.content) {
                  fullAnswer += data.content;
                  // Update last assistant message
                  setMessages((prev) => {
                    const last = prev[prev.length - 1];
                    if (last && last.role === 'assistant') {
                      return [...prev.slice(0, -1), { role: 'assistant', content: fullAnswer }];
                    }
                    return [...prev, { role: 'assistant', content: data.content }];
                  });
                } else if (data.type === 'done' && data.answer) {
                  setMessages((prev) => {
                    const last = prev[prev.length - 1];
                    if (last && last.role === 'assistant') {
                      return [...prev.slice(0, -1), { role: 'assistant', content: data.answer }];
                    }
                    return [...prev, { role: 'assistant', content: data.answer }];
                  });
                } else if (data.type === 'error') {
                  setMessages((prev) => [
                    ...prev,
                    { role: 'assistant', content: `Error: ${data.message}` },
                  ]);
                }
              } catch {
                // Skip non-JSON lines
              }
            }
          }
        }
      }

      if (!fullAnswer) {
        setMessages((prev) => [...prev, { role: 'assistant', content: 'No response received.' }]);
      }
    } catch (err) {
      setMessages((prev) => [...prev, { role: 'assistant', content: 'Failed to get response. Please check RAG configuration.' }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <Navbar />
      <main className="flex-1 max-w-4xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8 flex flex-col">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">RAG Research</h1>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto mb-4 space-y-4">
          {messages.length === 0 && (
            <div className="text-center text-gray-400 py-12">
              Ask questions about A-share investment research, reports, and analysis.
            </div>
          )}
          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-[80%] rounded-lg px-4 py-2 ${
                  msg.role === 'user'
                    ? 'bg-blue-600 text-white'
                    : 'bg-white border text-gray-800'
                }`}
              >
                <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
              </div>
            </div>
          ))}
          {loading && (
            <div className="flex justify-start">
              <div className="max-w-[80%] rounded-lg px-4 py-2 bg-white border text-gray-400">
                <p className="text-sm">Thinking...</p>
              </div>
            </div>
          )}
        </div>

        {/* Input */}
        <form onSubmit={handleQuery} className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask about stocks, reports, research..."
            className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-blue-300"
          >
            Send
          </button>
        </form>
      </main>
    </div>
  );
}
