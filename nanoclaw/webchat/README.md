# NanoClaw web chat

A small native channel for the NanoClaw v2 checkout on the `nanoclaw` LXC.
The browser talks directly to NanoClaw through Caddy at
`https://nanoclaw.tail.davegallant.ca/chat/`. OneCLI remains at `/`.

`web.ts` is installed as `src/channels/web.ts` and imported from
`src/channels/index.ts` with `import './web.js';`. The HTML is installed at
both `src/channels/web.html` and `dist/channels/web.html`; TypeScript does not
copy static assets during a build. Recopy it after rebuilding. Restart
`nanoclaw-v2-454ebe7e.service` after changes.

The channel listens only on `127.0.0.1:3200` and has one conversation,
`web/local`. Its messaging group is wired to the existing `cli-with-dave`
agent group. The agent session is distinct from the CLI session, but the
agent workspace and tools are shared. The host stores the last displayed
messages in `data/webchat.db`; the UI loads the newest 100 and receives new
messages by server-sent events. Include this database in NanoClaw backups.

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
