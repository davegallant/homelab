/** Personal browser channel for the NanoClaw v2 host. Caddy authenticates /chat. */
import { randomUUID } from 'node:crypto';
import { execFile } from 'node:child_process';
import { createServer, type IncomingMessage, type Server, type ServerResponse } from 'node:http';
import { readFileSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import Database from 'better-sqlite3';

import { CONTAINER_IMAGE, DATA_DIR } from '../config.js';
import { getDb } from '../db/connection.js';
import { getMessagingGroupByPlatform } from '../db/messaging-groups.js';
import { deleteSession, updateSession } from '../db/sessions.js';
import { sessionContextPath, sessionDir } from '../session-manager.js';
import type { ChannelAdapter, ChannelDefaults, ChannelSetup, OutboundMessage } from './adapter.js';
import { registerChannelAdapter } from './channel-registry.js';
import { log } from '../log.js';

const MAIN_ID = 'main';
const MAIN_PLATFORM_ID = 'local';
const SIDE_PLATFORM_ID = 'side';
const PORT = 3200;
const MAX_BODY = 16 * 1024;
const MAX_TEXT = 8000;
const HTML = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'web.html'), 'utf8');
const FAVICON = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'nanoclaw-favicon.png'));
const SIDE_ID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const execFileAsync = promisify(execFile);
const DEFAULTS: ChannelDefaults = {
  dm: { engageMode: 'pattern', engagePattern: '.', threads: false, unknownSenderPolicy: 'public' },
  group: { engageMode: 'pattern', engagePattern: '.', threads: true, sessionMode: 'per-thread', unknownSenderPolicy: 'public' },
  mentions: 'never',
};

type Chat = { id: string; title: string; created_at: string; updated_at: string };
type StoredMessage = { id: string; chat_id: string; role: 'user' | 'assistant'; text: string; created_at: string };

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
  const deleting = new Set<string>();

  function broadcast(value: unknown): void {
    for (const client of clients) {
      try { client.write(`data: ${JSON.stringify(value)}\n\n`); }
      catch { clients.delete(client); }
    }
  }

  function getChat(id: string): Chat | undefined {
    if (id !== MAIN_ID && !SIDE_ID_RE.test(id)) return undefined;
    return db!.prepare('SELECT id, title, created_at, updated_at FROM chats WHERE id = ?').get(id) as Chat | undefined;
  }

  function save(chatId: string, role: StoredMessage['role'], text: string): StoredMessage {
    const row: StoredMessage = { id: randomUUID(), chat_id: chatId, role, text, created_at: new Date().toISOString() };
    const chat = getChat(chatId);
    if (!chat || deleting.has(chatId)) throw new Error('Chat no longer exists');
    const title = role === 'user' && chatId !== MAIN_ID && chat.title === 'New chat'
      ? text.split('\n')[0].slice(0, 48) || 'New chat' : chat.title;
    db!.transaction(() => {
      db!.prepare('INSERT INTO messages (id, chat_id, role, text, created_at) VALUES (@id, @chat_id, @role, @text, @created_at)').run(row);
      db!.prepare('UPDATE chats SET title = ?, updated_at = ? WHERE id = ?').run(title, row.created_at, chatId);
    })();
    broadcast({ type: 'message', chat_id: chatId, message: row });
    if (title !== chat.title) broadcast({ type: 'chats-changed' });
    return row;
  }

  async function readBody(req: IncomingMessage): Promise<string> {
    let body = '';
    for await (const chunk of req) {
      body += chunk.toString('utf8');
      if (Buffer.byteLength(body) > MAX_BODY) throw new Error('Message too large');
    }
    return body;
  }

  function canWrite(req: IncomingMessage): boolean {
    return req.headers.origin === 'https://nanoclaw.tail.davegallant.ca'
      && req.headers['x-webchat-request'] === '1';
  }

  async function removeSessionFolder(agentGroupId: string, sessionId: string): Promise<void> {
    const dir = sessionDir(agentGroupId, sessionId);
    try {
      rmSync(dir, { recursive: true, force: true });
    } catch (err) {
      const code = (err as NodeJS.ErrnoException).code;
      if (code !== 'EACCES' && code !== 'EPERM') throw err;
      // Container setup leaves root-owned mount placeholders under extra/.
      // The NanoClaw user can ask its existing Docker image to return ownership.
      await execFileAsync('docker', [
        'run', '--rm', '--network', 'none', '--user', '0',
        '--mount', `type=bind,source=${dir},target=/session`,
        '--entrypoint', '/bin/chown', CONTAINER_IMAGE,
        '-R', `${process.getuid?.() ?? 1000}:${process.getgid?.() ?? 1000}`, '/session',
      ], { timeout: 30000 });
      rmSync(dir, { recursive: true, force: true });
    }
  }

  async function deleteSideChat(chatId: string): Promise<void> {
    if (chatId === MAIN_ID || !getChat(chatId)) throw new Error('Chat not found');
    if (deleting.has(chatId)) throw new Error('Chat is already being deleted');
    deleting.add(chatId);
    try {
      const sideGroup = await getMessagingGroupByPlatform('web', SIDE_PLATFORM_ID, 'web');
      if (!sideGroup) throw new Error('Side chat channel is not configured');
      const sessions = await getDb().all<{ id: string; agent_group_id: string }>(
        'SELECT id, agent_group_id FROM sessions WHERE messaging_group_id = ? AND thread_id = ?',
        sideGroup.id, chatId,
      );
      const { isContainerRunning, killContainer } = await import('../container-runner.js');
      for (const session of sessions) {
        await updateSession(session.id, { status: 'closed' });
        if (isContainerRunning(session.id)) {
          await new Promise<void>((resolve, reject) => {
            const timer = setTimeout(() => reject(new Error('Timed out stopping chat session')), 30000);
            killContainer(session.id, 'webchat-delete', () => { clearTimeout(timer); resolve(); });
          });
        }
        await removeSessionFolder(session.agent_group_id, session.id);
        rmSync(sessionContextPath(session.agent_group_id, session.id), { force: true });
        for (const table of ['pending_questions', 'pending_approvals', 'session_claims', 'delivery_attempts', 'wake_signals']) {
          await getDb().run(`DELETE FROM ${table} WHERE session_id = ?`, session.id);
        }
        await deleteSession(session.id);
      }
      db!.transaction(() => {
        db!.prepare('DELETE FROM messages WHERE chat_id = ?').run(chatId);
        db!.prepare('DELETE FROM chats WHERE id = ?').run(chatId);
      })();
      broadcast({ type: 'chat-deleted', chat_id: chatId });
    } finally {
      deleting.delete(chatId);
    }
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
    if (req.method === 'GET' && pathname === '/favicon.png') {
      res.writeHead(200, {
        'Content-Type': 'image/png',
        'Cache-Control': 'public, max-age=86400',
        'X-Content-Type-Options': 'nosniff',
      });
      res.end(FAVICON);
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
    if (req.method === 'GET' && pathname === '/api/chats') {
      const chats = db!.prepare("SELECT id, title, created_at, updated_at FROM chats ORDER BY (id = 'main') DESC, updated_at DESC").all();
      json(res, 200, { chats });
      return;
    }
    if (req.method === 'POST' && pathname === '/api/chats') {
      if (!canWrite(req)) { json(res, 403, { error: 'Forbidden' }); return; }
      const sideGroup = await getMessagingGroupByPlatform('web', SIDE_PLATFORM_ID, 'web');
      if (!sideGroup) { json(res, 503, { error: 'Side chat channel is not configured' }); return; }
      const now = new Date().toISOString();
      const chat: Chat = { id: randomUUID(), title: 'New chat', created_at: now, updated_at: now };
      db!.prepare('INSERT INTO chats (id, title, created_at, updated_at) VALUES (@id, @title, @created_at, @updated_at)').run(chat);
      broadcast({ type: 'chats-changed' });
      json(res, 201, chat);
      return;
    }
    const chatMatch = pathname.match(/^\/api\/chats\/([^/]+)$/);
    if (req.method === 'DELETE' && chatMatch) {
      if (!canWrite(req)) { json(res, 403, { error: 'Forbidden' }); return; }
      const chatId = chatMatch[1];
      if (chatId === MAIN_ID || !getChat(chatId)) { json(res, 404, { error: 'Chat not found' }); return; }
      await deleteSideChat(chatId);
      json(res, 200, { deleted: chatId });
      return;
    }
    const messageMatch = pathname.match(/^\/api\/chats\/([^/]+)\/messages$/);
    if (messageMatch) {
      const chatId = messageMatch[1];
      if (!getChat(chatId) || deleting.has(chatId)) { json(res, 404, { error: 'Chat not found' }); return; }
      if (req.method === 'GET') {
        const rows = db!.prepare('SELECT id, chat_id, role, text, created_at FROM messages WHERE chat_id = ? ORDER BY rowid DESC LIMIT 100').all(chatId);
        json(res, 200, { messages: rows.reverse() });
        return;
      }
      if (req.method === 'POST') {
        if (!canWrite(req)) { json(res, 403, { error: 'Forbidden' }); return; }
        if (!req.headers['content-type']?.startsWith('application/json')) { json(res, 415, { error: 'Expected JSON' }); return; }
        let input: unknown;
        try { input = JSON.parse(await readBody(req)); }
        catch (err) { json(res, err instanceof Error && err.message === 'Message too large' ? 413 : 400, { error: err instanceof Error ? err.message : 'Invalid JSON' }); return; }
        const value = input as Record<string, unknown> | null;
        const text = typeof value?.text === 'string' ? value.text.trim() : '';
        if (!text || text.length > MAX_TEXT) { json(res, 400, { error: `Message must be 1–${MAX_TEXT} characters` }); return; }
        const saved = save(chatId, 'user', text);
        await config.onInbound(chatId === MAIN_ID ? MAIN_PLATFORM_ID : SIDE_PLATFORM_ID, chatId === MAIN_ID ? null : chatId, {
          id: saved.id,
          kind: 'chat',
          timestamp: saved.created_at,
          isGroup: chatId !== MAIN_ID,
          content: { text, sender: 'Dave', senderId: 'web:dave' },
        });
        json(res, 202, saved);
        return;
      }
    }
    json(res, 404, { error: 'Not found' });
  }

  return {
    name: 'web', channelType: 'web', supportsThreads: true, defaults: DEFAULTS,
    async setup(config) {
      db = new Database(join(DATA_DIR, 'webchat.db'));
      db.pragma('journal_mode = WAL');
      db.exec('CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, role TEXT NOT NULL, text TEXT NOT NULL, created_at TEXT NOT NULL)');
      const columns = db.pragma('table_info(messages)') as Array<{ name: string }>;
      if (!columns.some((column) => column.name === 'chat_id')) {
        db.exec("ALTER TABLE messages ADD COLUMN chat_id TEXT NOT NULL DEFAULT 'main'");
      }
      db.exec('CREATE TABLE IF NOT EXISTS chats (id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)');
      const now = new Date().toISOString();
      db.prepare('INSERT OR IGNORE INTO chats (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)').run(MAIN_ID, 'Main', now, now);
      db.exec('CREATE INDEX IF NOT EXISTS messages_chat_id_idx ON messages(chat_id)');
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
    async deliver(platformId, threadId, message) {
      const chatId = platformId === MAIN_PLATFORM_ID ? MAIN_ID : platformId === SIDE_PLATFORM_ID ? threadId : null;
      if (!chatId || !getChat(chatId) || deleting.has(chatId)) return undefined;
      const text = textFrom(message);
      if (text !== null) save(chatId, 'assistant', text);
      return undefined;
    },
  };
}

registerChannelAdapter('web', { factory: createAdapter, defaults: DEFAULTS });
