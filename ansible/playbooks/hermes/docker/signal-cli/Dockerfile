# signal-cli sidecar for the Hermes gateway's Signal platform.
#
# Runs the official GraalVM native build (no JRE needed) as the JSON-RPC/SSE
# daemon Hermes talks to. Link state lives in /data (host-mounted at
# /root/signal-cli-data), so the one-time `signal-cli link` survives restarts
# and rebuilds. If no account is linked yet, the entrypoint idles instead of
# crash-looping (see entrypoint.sh).
#
# Built by the hermes playbook; version pinned via signal_cli_version in
# group_vars/all/vars.yaml and passed in as SIGNAL_CLI_VERSION.
FROM debian:13-slim

ARG SIGNAL_CLI_VERSION=0.14.8

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl jq \
    && curl -fsSL -o /tmp/signal-cli.tar.gz \
        "https://github.com/AsamK/signal-cli/releases/download/v${SIGNAL_CLI_VERSION}/signal-cli-${SIGNAL_CLI_VERSION}-Linux-native.tar.gz" \
    && tar -xzf /tmp/signal-cli.tar.gz -C /usr/local/bin \
    && rm /tmp/signal-cli.tar.gz \
    && apt-get purge -y --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh /usr/local/bin/signal-cli

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
