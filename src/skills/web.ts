import { assertSafeHttpUrl } from '../utils/network.js';
import { skillRegistry, type Skill } from './registry.js';

const USER_AGENT = 'Agent-02/4.20 (Self-Hosted AI Gateway)';

const webFetch: Skill = {
  name: 'web_fetch',
  description: 'Fetch text content from a public HTTP or HTTPS URL',
  requiresConsent: false,
  parameters: {
    type: 'object',
    properties: {
      url: { type: 'string', description: 'URL to fetch' },
    },
    required: ['url'],
  },
  async execute(args) {
    const url = await assertSafeHttpUrl(args.url);
    const response = await fetch(url, {
      headers: { 'User-Agent': USER_AGENT },
      signal: AbortSignal.timeout(15000),
    });

    if (!response.ok) {
      return `HTTP ${response.status}: ${response.statusText}`;
    }

    const text = await response.text();
    const cleaned = text
      .replace(/<script[\s\S]*?<\/script>/gi, '')
      .replace(/<style[\s\S]*?<\/style>/gi, '')
      .replace(/<[^>]+>/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();

    return cleaned.length > 8000 ? `${cleaned.slice(0, 8000)}\n...(truncated)` : cleaned;
  },
};

const webSearch: Skill = {
  name: 'web_search',
  description: 'Search the web using DuckDuckGo',
  requiresConsent: false,
  parameters: {
    type: 'object',
    properties: {
      query: { type: 'string', description: 'Search query' },
    },
    required: ['query'],
  },
  async execute(args) {
    const query = encodeURIComponent(args.query);
    const response = await fetch(`https://html.duckduckgo.com/html/?q=${query}`, {
      headers: { 'User-Agent': USER_AGENT },
      signal: AbortSignal.timeout(10000),
    });

    const html = await response.text();
    const results: string[] = [];
    const regex = /<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>([\s\S]*?)<\/a>/gi;
    let match: RegExpExecArray | null = null;

    while ((match = regex.exec(html)) && results.length < 8) {
      const title = match[2].replace(/<[^>]+>/g, '').trim();
      const href = match[1];
      if (title && href) {
        results.push(`- ${title}\n  ${href}`);
      }
    }

    return results.length > 0 ? results.join('\n\n') : 'No results found.';
  },
};

export function registerWebSkills(): void {
  skillRegistry.register(webFetch);
  skillRegistry.register(webSearch);
}
