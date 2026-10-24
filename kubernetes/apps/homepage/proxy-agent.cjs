"use strict";

const http = require("node:http");
const https = require("node:https");
const { syncBuiltinESMExports } = require("node:module");

const proxy = process.env.HOMEPAGE_TAILNET_PROXY;
const allowedHost = process.env.HOMEPAGE_ALLOWED_HOSTS?.split(",")[0];
const tailnetDomain = allowedHost?.slice(allowedHost.indexOf(".") + 1).toLowerCase();

if (!proxy || !tailnetDomain || tailnetDomain === allowedHost) {
  throw new Error("Homepage tailnet proxy settings are incomplete");
}

const directHosts = new Set(["localhost", "127.0.0.1", "::1", ".svc", ".cluster.local"]);

for (const [name, value] of Object.entries(process.env)) {
  if (!/^HOMEPAGE_VAR_.*_URL$/.test(name)) continue;

  try {
    const hostname = new URL(value).hostname.toLowerCase();
    if (hostname !== tailnetDomain && !hostname.endsWith(`.${tailnetDomain}`)) {
      directHosts.add(hostname);
    }
  } catch {
    // Homepage reports malformed service URLs through its normal widget errors.
  }
}

const proxyEnv = {
  HTTP_PROXY: proxy,
  HTTPS_PROXY: proxy,
  NO_PROXY: [...directHosts].join(","),
};

const HttpAgent = http.Agent;
const HttpsAgent = https.Agent;

http.Agent = class TailnetHttpAgent extends HttpAgent {
  constructor(options = {}) {
    super({ ...options, proxyEnv: options.proxyEnv ?? proxyEnv });
  }
};

https.Agent = class TailnetHttpsAgent extends HttpsAgent {
  constructor(options = {}) {
    super({ ...options, proxyEnv: options.proxyEnv ?? proxyEnv });
  }
};

// ws supplies createConnection for WebSocket upgrades, which bypasses the
// agent's proxy routing. Let the agent connect for tailnet upgrades instead.
for (const transport of [http, https]) {
  const request = transport.request;
  transport.request = function tailnetWebSocketRequest(options, ...args) {
    const hostname = (options.hostname ?? options.host ?? "").toLowerCase();
    if (options.headers?.Upgrade?.toLowerCase() === "websocket" &&
        (hostname === tailnetDomain || hostname.endsWith(`.${tailnetDomain}`))) {
      const { createConnection: _unused, ...proxiedOptions } = options;
      return request.call(this, { ...proxiedOptions, agent: new transport.Agent() }, ...args);
    }
    return request.call(this, options, ...args);
  };
}

syncBuiltinESMExports();
