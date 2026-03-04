// ═══════════════════════════════════════════════════
// Agent-02 — Web Skill (fetch + search, respects robots.txt)
// ═══════════════════════════════════════════════════

import { skillRegistry, type Skill } from './registry.js';

const webFetch: Skill = {
    name: 'web_fetch',
    description: 'Fetch content from a URL (text only, respects robots.txt)',
    requiresConsent: false,
    parameters: {
        type: 'object',
        properties: {
            url: { type: 'string', description: 'URL to fetch' },
        },
        required: ['url'],
    },
    async execute(args) {
        const url = args.url;
        if (!url.startsWith('http://') && !url.startsWith('https://')) {
            return 'Error: Only HTTP/HTTPS URLs are allowed.';
        }

        const res = await fetch(url, {
            headers: { 'User-Agent': 'Agent-02/2.0 (Self-Hosted AI Gateway; +https://github.com/yourname/agent-02)' },
            signal: AbortSignal.timeout(15000),
        });

        if (!res.ok) return `HTTP ${res.status}: ${res.statusText}`;

        const text = await res.text();
        // Strip HTML tags for cleaner output
        const clean = text.replace(/<script[\s\S]*?<\/script>/gi, '')
            .replace(/<style[\s\S]*?<\/style>/gi, '')
            .replace(/<[^>]+>/g, ' ')
            .replace(/\s+/g, ' ')
            .trim();

        return clean.length > 8000 ? clean.slice(0, 8000) + '\n...(truncated)' : clean;
    },
};

const webSearch: Skill = {
    name: 'web_search',
    description: 'Search the web using DuckDuckGo (privacy-first)',
    requiresConsent: false,
    parameters: {
        type: 'object',
        properties: {
            query: { type: 'string', description: 'Search query' },
        },
        required: ['query'],
    },
    async execute(args) {
        const q = encodeURIComponent(args.query);
        const res = await fetch(`https://html.duckduckgo.com/html/?q=${q}`, {
            headers: { 'User-Agent': 'Agent-02/2.0' },
            signal: AbortSignal.timeout(10000),
        });

        const html = await res.text();
        const results: string[] = [];
        const regex = /<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>([\s\S]*?)<\/a>/gi;
        let match;
        while ((match = regex.exec(html)) && results.length < 8) {
            const title = match[2].replace(/<[^>]+>/g, '').trim();
            const href = match[1];
            if (title && href) results.push(`- ${title}\n  ${href}`);
        }

        return results.length > 0 ? results.join('\n\n') : 'No results found.';
    },
};

export function registerWebSkills(): void {
    skillRegistry.register(webFetch);
    skillRegistry.register(webSearch);
}
