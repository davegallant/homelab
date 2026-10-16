# NanoClaw web chat

A small native channel for the NanoClaw v2 checkout on the `nanoclaw` LXC.
The browser talks directly to NanoClaw through Caddy at
`https://nanoclaw.tail.davegallant.ca/chat/`. OneCLI remains at `/`.

`web.ts` is installed as `src/channels/web.ts` and imported from
`src/channels/index.ts` with `import './web.js';`. The HTML and NanoClaw favicon
are installed at both `src/channels/` and `dist/channels/`; TypeScript does not
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

Deleting a side chat stops its container, removes its session directory and
context file, deletes its central session row, then removes its web messages
and chat row. Some session mount placeholders are root owned; the adapter uses
the existing NanoClaw Docker image to return ownership before removing them.
Main has no Delete control. Shared agent workspace files and retained backups
are outside this delete operation.

The live Caddyfile is `/root/tailnet-caddy/Caddyfile`. It routes `/chat/*`
to `127.0.0.1:3200` with HTTP Basic authentication and all other paths to
OneCLI at `172.17.0.1:10254`. The password is in
`/root/tailnet-caddy/webchat-password` (root only); only its bcrypt hash is
in the Caddyfile. The live Caddyfile was backed up as
`/root/tailnet-caddy/Caddyfile.pre-webchat` before editing. Its route block is:

```caddyfile
handle /chat {
  redir * /chat/ 308
}
handle_path /chat/* {
  basic_auth {
    dave <bcrypt hash from caddy hash-password>
  }
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
