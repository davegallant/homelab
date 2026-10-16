# NanoClaw web chat

A small native channel for the NanoClaw v2 checkout on the `nanoclaw` LXC.
The browser talks directly to NanoClaw through Caddy at
`https://nanoclaw.tail.davegallant.ca/chat/`. OneCLI remains at `/`.

`web.ts` is installed as `src/channels/web.ts` and imported from
`src/channels/index.ts` with `import './web.js';`. Both HTML files and
`favicon-32x32.png` from `https://nanoclaw.dev/favicon-32x32.png` are installed
at both `src/channels/` and `dist/channels/`; TypeScript does not
copy static assets during a build. Recopy them after rebuilding. Restart
`nanoclaw-v2-454ebe7e.service` after changes.

The channel listens only on `127.0.0.1:3200`. Main uses the original
`web/local` messaging group and session. Side chats use the `web/side`
messaging group with one NanoClaw thread and session per chat. Both groups
are wired to `cli-with-dave`, so agent tools and workspace files are shared
while conversation context is separate. Create the side routing on a new LXC:

```sh
./bin/ncl messaging-groups create --channel-type web --platform-id side --instance web --name "Web Side Chats" --is-group 1 --unknown-sender-policy public
./bin/ncl wirings create --channel-type web --platform-id side --instance web --agent-group cli-with-dave --engage-mode pattern --engage-pattern . --sender-scope all --session-mode per-thread --threads true
```

The host stores all browser messages and chat titles in `data/webchat.db`.
There is no automatic expiry. The UI loads the newest 100 messages per chat
and receives new ones by server-sent events. Existing single-chat messages
are migrated to Main on first launch. Include this database in NanoClaw
backups.

`/chat/login` is a standard HTML sign-in form for password managers. The
server checks the password against the scrypt hash in `data/webchat-auth.json`
(owned by `nanoclaw`, mode `0600`), then issues a 14-day session cookie with
`Secure`, `HttpOnly`, `SameSite=Lax`, and `Path=/chat/`. Only a hash of the
session token is stored in `data/webchat.db`; logout removes it. The chat page,
API, and event stream require a valid session. Login is limited to ten failed
attempts per 15 minutes per service process. Back up the auth file with the
database; the service cannot start without it. The existing chat password was
reused when the auth file was created on the LXC.

Deleting a side chat stops its container, removes its session directory and
context file, deletes its central session row, then removes its web messages
and chat row. Some session mount placeholders are root owned; the adapter uses
the existing NanoClaw Docker image to return ownership before removing them.
Main has no Delete control. Shared agent workspace files and retained backups
are outside this delete operation.

The live Caddyfile is `/root/tailnet-caddy/Caddyfile`. It routes `/chat/*`
to `127.0.0.1:3200` and all other paths to OneCLI at `172.17.0.1:10254`.
The NanoClaw channel enforces authentication on every chat route. Caddyfile
backups are `/root/tailnet-caddy/Caddyfile.pre-webchat` and
`/root/tailnet-caddy/Caddyfile.pre-form-login` (the latter has the old Basic
auth configuration). Its route block is:

```caddyfile
handle /chat {
  redir * /chat/ 308
}
handle_path /chat/* {
  reverse_proxy 127.0.0.1:3200
}
handle {
  reverse_proxy 172.17.0.1:10254
}
```

Check `docker exec tailnet-caddy caddy validate --config /etc/caddy/Caddyfile
--adapter caddyfile` before reloading Caddy. The host is absent from the
Ansible inventory, so the Caddy route and NanoClaw channel are currently
manually deployed. Preserve this directory and the remote NanoClaw checkout
when rebuilding the LXC.
