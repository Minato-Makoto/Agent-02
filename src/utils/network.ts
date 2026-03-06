import * as dns from 'dns/promises';
import * as net from 'net';

const PRIVATE_V4_PATTERNS = [
  /^10\./,
  /^127\./,
  /^169\.254\./,
  /^172\.(1[6-9]|2\d|3[0-1])\./,
  /^192\.168\./,
];

function isPrivateIpv4(host: string): boolean {
  return PRIVATE_V4_PATTERNS.some((pattern) => pattern.test(host));
}

function isPrivateIpv6(host: string): boolean {
  const normalized = host.toLowerCase();
  return (
    normalized === '::1' ||
    normalized.startsWith('fc') ||
    normalized.startsWith('fd') ||
    normalized.startsWith('fe80:')
  );
}

function isLocalHostname(hostname: string): boolean {
  const normalized = hostname.toLowerCase();
  return normalized === 'localhost' || normalized.endsWith('.local');
}

export async function assertSafeHttpUrl(rawUrl: string): Promise<URL> {
  let parsed: URL;

  try {
    parsed = new URL(rawUrl);
  } catch {
    throw new Error('Invalid URL.');
  }

  if (!['http:', 'https:'].includes(parsed.protocol)) {
    throw new Error('Only HTTP and HTTPS URLs are allowed.');
  }

  if (isLocalHostname(parsed.hostname)) {
    throw new Error('Access denied: local network targets are blocked.');
  }

  const directFamily = net.isIP(parsed.hostname);
  if ((directFamily === 4 && isPrivateIpv4(parsed.hostname)) || (directFamily === 6 && isPrivateIpv6(parsed.hostname))) {
    throw new Error('Access denied: private IP ranges are blocked.');
  }

  const resolved = await dns.lookup(parsed.hostname, { all: true });
  for (const entry of resolved) {
    if ((entry.family === 4 && isPrivateIpv4(entry.address)) || (entry.family === 6 && isPrivateIpv6(entry.address))) {
      throw new Error('Access denied: private IP ranges are blocked.');
    }
  }

  return parsed;
}
