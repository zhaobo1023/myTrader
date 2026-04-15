/** Default SSE stream timeout in milliseconds (5 minutes). */
const DEFAULT_SSE_TIMEOUT_MS = 5 * 60 * 1000;

/**
 * useSSEFetch - fetch-based SSE reader that supports POST requests.
 *
 * EventSource only supports GET; this hook uses fetch + ReadableStream
 * to parse the SSE protocol manually, allowing POST with a JSON body.
 *
 * A default 5-minute timeout is applied unless the caller passes its own
 * AbortSignal (e.g. AbortSignal.timeout(ms) or a controller signal).
 */
export function useSSEFetch() {
  const stream = async (
    url: string,
    body: object,
    onEvent: (event: Record<string, unknown> & { type?: string }) => void,
    signal?: AbortSignal,
  ): Promise<void> => {
    // Use caller-supplied signal, or fall back to a default timeout.
    const effectiveSignal = signal ?? AbortSignal.timeout(DEFAULT_SSE_TIMEOUT_MS);

    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: effectiveSignal,
    });

    if (!resp.ok) {
      throw new Error(`SSE request failed: ${resp.status} ${resp.statusText}`);
    }

    const reader = resp.body?.getReader();
    if (!reader) throw new Error('Response body is not readable');

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n\n');
      buffer = parts.pop() ?? '';

      for (const chunk of parts) {
        for (const line of chunk.split('\n')) {
          if (line.startsWith('data: ')) {
            try {
              onEvent(JSON.parse(line.slice(6)));
            } catch {
              // skip malformed event
            }
          }
        }
      }
    }
  };

  return { stream };
}
