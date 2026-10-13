// A small, strict parser for server-sent events read from a fetch() stream (EventSource cannot send our Authorization header).
export type SseMessage = { event: string; data: string };

export class SseParser {
    private pending = '';
    private skipping = false;
    private limit: number;
    constructor(limit = 2_000_000) { this.limit = limit; }

    push(chunk: string): SseMessage[] {
        this.pending += chunk;
        const out: SseMessage[] = [];
        for (;;) {
            const match = /\r?\n\r?\n/.exec(this.pending);
            if (!match) break;
            const block = this.pending.slice(0, match.index);
            this.pending = this.pending.slice(match.index + match[0].length);
            if (this.skipping) { this.skipping = false; continue; }
            const message = parseBlock(block);
            if (message) out.push(message);
        }
        if (this.pending.length > this.limit) { this.pending = ''; this.skipping = true; }
        return out;
    }
}

function parseBlock(block: string): SseMessage | null {
    let event = 'message';
    const data: string[] = [];
    let comment = false;
    for (const line of block.split(/\r?\n/)) {
        if (line.startsWith(':')) comment = true;
        else if (line.startsWith('event:')) event = line.slice(6).trim();
        else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''));
    }
    if (data.length) return { event, data: data.join('\n') };
    return comment ? { event: 'comment', data: '' } : null;
}
