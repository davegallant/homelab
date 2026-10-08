#!/bin/sh
# signal-cli sidecar entrypoint.
#
# If no account has been linked yet, idle instead of crash-looping the
# daemon: linking is a one-time manual step (see the message below).
set -eu

: "${SIGNAL_CLI_ACCOUNT:?SIGNAL_CLI_ACCOUNT must be set (your Signal number, E.164)}"

ACCOUNTS_JSON="/data/data/accounts.json"

if [ ! -s "${ACCOUNTS_JSON}" ]; then
    echo "No linked Signal account data in /data yet."
    echo "Link it once, then restart this container:"
    echo "  docker stop signal-cli"
    echo "  docker run --rm -it --entrypoint /usr/local/bin/signal-cli -v /root/signal-cli-data:/data <signal-cli-image> --config /data link -n HermesAgent"
    echo "  # scan the tsdevice URI with Signal on your phone: Settings -> Linked devices -> +"
    echo "  # leave the link command running until it exits on its own"
    echo "  docker start signal-cli"
    exec sleep infinity
fi

# signal-cli >= 0.14 identifies local accounts by UUID (ACI); --account no
# longer resolves E.164 numbers ("User ... is not registered"). Resolve the
# UUID for the configured number from accounts.json.
ACCOUNT_UUID=$(jq -r --arg num "${SIGNAL_CLI_ACCOUNT}" \
    '.accounts[] | select(.number == $num) | .uuid' \
    "${ACCOUNTS_JSON}" 2>/dev/null | head -n 1 || true)

if [ -z "${ACCOUNT_UUID}" ] || [ "${ACCOUNT_UUID}" = "null" ]; then
    echo "No account matching ${SIGNAL_CLI_ACCOUNT} in ${ACCOUNTS_JSON}; idling."
    exec sleep infinity
fi

exec /usr/local/bin/signal-cli --config /data --account "${ACCOUNT_UUID}" daemon --http 0.0.0.0:8080
