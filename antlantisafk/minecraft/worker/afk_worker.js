'use strict';
/**
 * AntlantisAFK — Node.js mineflayer/minecraft-protocol worker.
 *
 * Runs as a child process of the Python GUI. Speaks newline-delimited JSON
 * on stdin/stdout (see antlantisafk/minecraft/worker_bridge.py).
 *
 * STRICT PASSIVITY CONTRACT (enforced here):
 * - This worker NEVER sends movement, look, swing, use-item, interact,
 *   mine, or command packets. There is deliberately no code path that
 *   could. It exists to open an authenticated session and answer
 *   keep-alives, nothing more.
 * - The Minecraft access token arrives via the stdin handshake and lives
 *   only in this process's memory. It is never logged or written to disk.
 * - Error text is sanitised before leaving this process so tokens can
 *   never leak into logs.
 */

const PASSIVITY_NOTE =
  'AntlantisAFK worker: passive AFK client (keep-alives only). No gameplay automation is implemented by design.';

let mc; // minecraft-protocol, required lazily with a friendly error

/** Strip token-like blobs from any text before it leaves the worker. */
function sanitize(text) {
  return String(text ?? '').replace(/[A-Za-z0-9._-]{24,}/g, '[REDACTED]');
}

function emit(obj) {
  try {
    process.stdout.write(JSON.stringify(obj) + '\n');
  } catch (err) {
    // stdout closed; the parent will notice and stop us.
  }
}

function emitLog(level, message) {
  emit({ type: 'log', level, message: sanitize(message) });
}

function emitEvent(event, data) {
  emit({ type: 'event', event, data: data || {} });
}

/** Send a response for a request previously received on stdin. */
function respond(id, ok, data, error) {
  const msg = { type: 'response', id, ok };
  if (ok) msg.data = data || {};
  else msg.error = sanitize(error || 'unknown worker error');
  emit(msg);
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let auth = null; // { accessToken, username, uuid } from the handshake
let client = null; // active minecraft-protocol client
let joinMessage = ''; // optional single post-join message (user-configured)
let joinMessageSent = false;
let shuttingDown = false;

// ---------------------------------------------------------------------------
// Connection
// ---------------------------------------------------------------------------

function destroyClient() {
  if (client) {
    try { client.end('disconnect'); } catch (_) { /* ignore */ }
    client.removeAllListeners();
    client = null;
  }
  joinMessageSent = false;
}

function startConnection(args) {
  const host = String(args.host || '');
  const port = parseInt(String(args.port || '25565'), 10);
  const version = String(args.version || 'auto');
  joinMessage = String(args.joinMessage || '');
  joinMessageSent = false;

  if (!auth || !auth.accessToken) {
    throw new Error('Not authenticated: no token handshake received.');
  }
  if (!host) throw new Error('Server address is required.');
  if (!Number.isFinite(port) || port < 1 || port > 65535) {
    throw new Error('Port must be between 1 and 65535.');
  }

  destroyClient();

  const options = {
    host,
    port,
    username: auth.username,
    version: version === 'auto' || version === '' ? false : version,
    hideErrors: true,
    // We never chat or sign anything; skip fetching Mojang chat-signing keys.
    disableChatSigning: true,
    // Keep-alive handling: nmp answers server keep-alives automatically and
    // closes the connection after ~120s without server pings.
    keepAlive: true,
    // Custom auth: use the Microsoft token provided by the Python side via
    // the stdin handshake. No password is ever handled — by design there is
    // no code path that could accept one.
    auth: (clientInstance, opts) => {
      opts.haveCredentials = true;
      opts.accessToken = auth.accessToken;
      clientInstance.session = {
        accessToken: auth.accessToken,
        selectedProfile: {
          name: auth.username,
          id: auth.uuid,
        },
      };
      clientInstance.uuid = auth.uuid;
      clientInstance.username = auth.username;
      opts.connect(clientInstance);
    },
  };

  client = mc.createClient(options);

  client.on('playerJoin', () => {
    emitEvent('connected', { username: auth.username });
    maybeSendJoinMessage();
  });
  // Fallback for versions/servers where playerJoin does not fire.
  client.on('login', () => {
    emitEvent('connected', { username: auth.username });
    maybeSendJoinMessage();
  });
  client.on('end', (reason) => {
    emitEvent('end', { reason: sanitize(typeof reason === 'string' ? reason : 'connection closed') });
  });
  client.on('kicked', (reason) => {
    emitEvent('kicked', { reason: sanitize(typeof reason === 'string' ? reason : JSON.stringify(reason || {})) });
  });
  client.on('error', (err) => {
    emitEvent('error', { message: sanitize(err && err.message ? err.message : String(err)) });
  });
}

/** Send the optional join message ONCE, if the user configured one. */
function maybeSendJoinMessage() {
  if (joinMessageSent || !joinMessage) return;
  joinMessageSent = true;
  // Small delay so the server finishes spawning the player.
  setTimeout(() => {
    if (!client) return;
    try {
      // Deliberately at most ONE message per join. This app contains no
      // chat-spam functionality and refuses to implement it.
      client.chat(String(joinMessage).slice(0, 256));
      emitLog('info', 'Join message sent (once).');
    } catch (err) {
      emitLog('warning', 'Could not send join message: ' + sanitize(err.message));
    }
  }, 2500);
}

// ---------------------------------------------------------------------------
// Command loop (stdin)
// ---------------------------------------------------------------------------

function handleCommand(msg) {
  const id = typeof msg.id === 'number' ? msg.id : -1;
  const cmd = String(msg.cmd || '');
  const args = msg.args || {};

  switch (cmd) {
    case 'ping_worker':
      respond(id, true, { ok: true, uptime: process.uptime(), note: PASSIVITY_NOTE });
      break;
    case 'auth_handshake':
      auth = {
        accessToken: String(args.accessToken || ''),
        username: String(args.username || ''),
        uuid: String(args.uuid || ''),
      };
      if (!auth.accessToken) {
        respond(id, false, null, 'Handshake rejected: access token missing.');
      } else {
        emitLog('info', 'Token handshake accepted (token kept in memory only).');
        respond(id, true, { ready: true });
      }
      break;
    case 'connect':
      try {
        startConnection(args);
        respond(id, true, { connecting: true });
      } catch (err) {
        destroyClient();
        respond(id, false, null, err && err.message ? err.message : String(err));
      }
      break;
    case 'disconnect':
      destroyClient();
      respond(id, true, { disconnected: true });
      break;
    default:
      respond(id, false, null, 'Unknown command: ' + cmd);
  }
}

function main() {
  process.title = 'AntlantisAFK-worker';

  let buffer = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (chunk) => {
    buffer += chunk;
    let idx;
    while ((idx = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + 1);
      if (!line) continue;
      let msg;
      try {
        msg = JSON.parse(line);
      } catch (_) {
        continue; // ignore malformed lines
      }
      if (msg && msg.type === 'shutdown') {
        shuttingDown = true;
        destroyClient();
        process.exit(0);
        return;
      }
      if (msg && typeof msg.cmd === 'string') {
        handleCommand(msg);
      }
    }
  });
  process.stdin.on('end', () => {
    // Parent closed the pipe: exit cleanly.
    destroyClient();
    process.exit(0);
  });
  process.on('SIGINT', () => { destroyClient(); process.exit(0); });
  process.on('SIGTERM', () => { destroyClient(); process.exit(0); });

  try {
    mc = require('minecraft-protocol');
  } catch (err) {
    emitLog('error',
      "The 'minecraft-protocol' npm package is missing. In this worker folder " +
      "run: npm install minecraft-protocol   (see README 'Troubleshooting').");
    process.exit(2);
  }

  emitLog('info', PASSIVITY_NOTE);
  emitLog('info', 'Worker ready. Awaiting token handshake and connect command.');
}

main();
