/** Personal browser channel for the NanoClaw v2 host. Caddy authenticates /chat. */
import { randomUUID } from 'node:crypto';
import { createServer, type IncomingMessage, type Server, type ServerResponse } from 'node:http';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import Database from 'better-sqlite3';

import { DATA_DIR } from '../config.js';
import type { ChannelAdapter, ChannelDefaults, ChannelSetup, OutboundMessage } from './adapter.js';
import { registerChannelAdapter } from './channel-registry.js';
import { log } from '../log.js';

const PLATFORM_ID = 'local';
const PORT = 3200;
const MAX_BODY = 16 * 1024;
const MAX_TEXT = 8000;
const HTML = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'web.html'), 'utf8');
const DEFAULTS: ChannelDefaults = {
  dm: { engageMode: 'pattern', engagePattern: '.', threads: false, unknownSenderPolicy: 'public' },
  group: { engageMode: 'pattern', engagePattern: '.', threads: false, unknownSenderPolicy: 'public' },
  mentions: 'never',
};

type StoredMessage = { id: string; role: 'user' | 'assistant'; text: string; created_at: string };

function json(res: ServerResponse, status: number, value: unknown): void {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
  res.end(JSON.stringify(value));
}

function textFrom(message: OutboundMessage): string | null {
  const content = message.content as Record<string, unknown> | string | undefined;
  if (typeof content === 'string') return content;
  return content && typeof content.text === 'string' ? content.text : null;
}

function createAdapter(): ChannelAdapter {
  let server: Server | null = null;
  let db: Database.Database | null = null;
  const clients = new Set<ServerResponse>();

  function save(role: StoredMessage['role'], text: string): StoredMessage {
    const row: StoredMessage = { id: randomUUID(), role, text, created_at: new Date().toISOString() };
    db!.prepare('INSERT INTO messages (id, role, text, created_at) VALUES (@id, @role, @text, @created_at)').run(row);
    for (const client of clients) client.write(`data: ${JSON.stringify(row)}\n\n`);
    return row;
  }

  async function handle(req: IncomingMessage, res: ServerResponse, config: ChannelSetup): Promise<void> {
    const pathname = new URL(req.url ?? '/', 'http://localhost').pathname;
    if (req.method === 'GET' && pathname === '/') {
      res.writeHead(200, {
        'Content-Type': 'text/html; charset=utf-8',
        'Cache-Control': 'no-store',
        'Content-Security-Policy': "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
        'X-Content-Type-Options': 'nosniff',
      });
      res.end(HTML);
      return;
    }
    if (req.method === 'GET' && pathname === '/api/messages') {
      const rows = db!.prepare('SELECT id, role, text, created_at FROM messages ORDER BY rowid DESC LIMIT 100').all();
      json(res, 200, { messages: rows.reverse() });
      return;
    }
    if (req.method === 'GET' && pathname === '/events') {
      res.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache, no-transform',
        Connection: 'keep-alive',
        'X-Accel-Buffering': 'no',
      });
      res.write(': connected\n\n');
      clients.add(res);
      req.on('close', () => clients.delete(res));
      return;
    }
    if (req.method === 'POST' && pathname === '/api/messages') {
      // Caddy authenticates the route; Origin and a custom header block cross-site posts.
      const origin = req.headers.origin;
      if (!origin || origin !== 'https://nanoclaw.tail.davegallant.ca' || req.headers['x-webchat-request'] !== '1') {
        json(res, 403, { error: 'Forbidden' });
        return;
      }
      if (!req.headers['content-type']?.startsWith('application/json')) {
        json(res, 415, { error: 'Expected JSON' });
        return;
      }
      let body = '';
      for await (const chunk of req) {
        body += chunk.toString('utf8');
        if (Buffer.byteLength(body) > MAX_BODY) {
          json(res, 413, { error: 'Message too large' });
          return;
        }
      }
      let input: unknown;
      try { input = JSON.parse(body); } catch { json(res, 400, { error: 'Invalid JSON' }); return; }
      const value = input as Record<string, unknown> | null;
      const text = typeof value?.text === 'string' ? value.text.trim() : '';
      if (!text || text.length > MAX_TEXT) {
        json(res, 400, { error: `Message must be 1–${MAX_TEXT} characters` });
        return;
      }
      const saved = save('user', text);
      await config.onInbound(PLATFORM_ID, null, {
        id: saved.id,
        kind: 'chat',
        timestamp: saved.created_at,
        content: { text, sender: 'Dave', senderId: 'web:dave' },
      });
      json(res, 202, saved);
      return;
    }
    json(res, 404, { error: 'Not found' });
  }

  return {
    name: 'web', channelType: 'web', supportsThreads: false, defaults: DEFAULTS,
    async setup(config) {
      db = new Database(join(DATA_DIR, 'webchat.db'));
      db.pragma('journal_mode = WAL');
      db.exec('CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, role TEXT NOT NULL, text TEXT NOT NULL, created_at TEXT NOT NULL)');
      server = createServer((req, res) => {
        void handle(req, res, config).catch((err) => {
          log.error('Web chat request failed', { err });
          if (!res.headersSent) json(res, 500, { error: 'Server error' });
          else res.end();
        });
      });
      await new Promise<void>((resolve, reject) => {
        server!.once('error', reject);
        server!.listen(PORT, '127.0.0.1', resolve);
      });
      log.info('Web chat listening', { port: PORT });
    },
    async teardown() {
      for (const client of clients) client.end();
      clients.clear();
      if (server) await new Promise<void>((resolve) => server!.close(() => resolve()));
      server = null;
      db?.close();
      db = null;
    },
    isConnected: () => server !== null,
    async deliver(platformId, _threadId, message) {
      if (platformId !== PLATFORM_ID) return undefined;
      const text = textFrom(message);
      if (text !== null) save('assistant', text);
      return undefined;
    },
  };
}

registerChannelAdapter('web', { factory: createAdapter, defaults: DEFAULTS });
