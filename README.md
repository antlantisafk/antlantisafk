# AtlantisAFK

![AtlantisAFK](assets/wordmark.png)

A personal, single-account **AFK companion for Minecraft: Java Edition**.
It keeps **one** Microsoft/Minecraft account (yours) connected to **one**
server and responds only to keep-alive packets. It is an AFK client, not a
bot: there is **no** movement, mining, combat, chat automation, or any other
gameplay automation — by design, such code paths do not exist.

## 🚀 Quick start (most users)

1. Download **`AtlantisAFK.exe`** from
   [Releases](https://github.com/antlantisafk/antlantisafk/releases) —
   everything (Node.js runtime, protocol library, branding) is bundled.
   No Python, no Node, no setup.
2. Run it, click **Login with Microsoft**, complete the browser sign-in.
3. Type your server address and click **Start AFK**.

> **Note:** new Microsoft-app registrations require a one-time allow-list
> review by Mojang before `login_with_xbox` works
> ([policy](https://aka.ms/AppRegInfo)). Until the bundled AppID is approved
> you may see *"Invalid app registration"* at the final login step — this is
> expected and temporary. See [Troubleshooting](#troubleshooting).

---

- **Platform:** Windows 10/11 (Python 3.11+; GUI via PySide6)
- **Auth:** official Microsoft OAuth 2.0 device-code flow (you sign in with
  your own Microsoft account in your browser; the app never sees your
  password)
- **Connection:** a bundled Node.js worker using `minecraft-protocol`,
  launched and controlled by the Python app. The worker is strictly passive:
  it answers keep-alives and nothing else.
- **Token storage:** the refresh token lives only in **Windows Credential
  Manager** (or an encrypted DPAPI blob fallback), never in the config file.

---

## ⚠️ Legal & Safety Disclaimer

- **Use only on servers where AFK is explicitly allowed.** Many servers ban
  AFK clients or unattended accounts. AFK clients **may violate a server's
  rules** — check them first. You are responsible for complying with the
  rules of any server you connect to.
- **Use only your own account.** AntlantisAFK authenticates exclusively via
  the official Microsoft device-code flow for the account you sign in with.
- **What this app will never do (by design):**
  - accept or import raw session IDs, access tokens, or refresh tokens
  - ask for a Microsoft password
  - support multiple accounts, account switching, or proxy rotation
  - bypass anti-AFK systems, movement detection, chat filters, or any server
    rule enforcement
  - move, mine, fight, use items, interact with entities, or send chat spam
- Using automation that violates the Minecraft EULA or a server's rules can
  get your account or IP banned. This tool deliberately does as little as
  possible: connect, answer keep-alives, stay online.

---

## Project structure

```
AntlantisAFK/
├── main.py                     # entry point
├── antlantisafk/
│   ├── config.py               # TOML config load/save + validation
│   ├── logging_setup.py        # rotating file logs (5 MB × 3)
│   ├── status.py               # account/connection status enums
│   ├── constants.py            # paths, identifiers
│   ├── auth/                   # Microsoft device-code → Xbox → Minecraft
│   ├── security/               # token store, single-instance guard
│   ├── minecraft/              # session state machine, worker bridge
│   │   └── worker/afk_worker.js  # passive Node.js worker (keep-alives only)
│   ├── gui/                    # PySide6 main window, login dialog, tray
│   └── utils/                  # validators
├── tests/                      # unit tests (pytest)
├── build.py / build.bat        # PyInstaller packaging
└── config.example.toml         # documented example configuration
```

## Setup

### 1. Prerequisites

- **Python 3.11+** — <https://www.python.org/downloads/> (tick *"Add to
  PATH"* during install; on Windows use the `py` launcher)
- **Node.js LTS (18 or newer)** — <https://nodejs.org/> — required only for
  the Minecraft connection worker, not for auth/tests/GUI.

### 2. Install Python dependencies

```bat
cd AntlantisAFK
py -3 -m pip install -r requirements.txt
```

### 3. Install the worker dependency (one time)

```bat
cd antlantisafk\minecraft\worker
npm install
cd ..\..\..
```

This downloads `minecraft-protocol` into `antlantisafk/minecraft/worker/`.

### 4. Setup: Azure app registration (one time, free, ~5 minutes)

The device-code flow needs an *application (client) ID* that identifies this
app to Microsoft's login servers. It is **not a secret**.

1. Go to <https://aka.ms/appregistrations> (the direct link to
   **App registrations**).
2. Click **+ New registration**. Name: `AntlantisAFK` (anything works).
3. **Supported account types:** choose **"Personal Microsoft accounts only"**
   — Minecraft's API (`login_with_xbox`) rejects tokens issued under the
   multi-audience setting with "Invalid app registration" (HTTP 403).
4. No redirect URI needed. Click **Register**.
5. On the app's **Overview** page copy the **Application (client) ID**.
6. Enable the device flow: **Authentication** → **Settings** tab →
   **"Allow public client flows"** → **Enabled** → **Save**.
7. After changing the audience, wait a couple of minutes before logging in —
   Microsoft's token services take a moment to pick up the change.
7. Provide the ID to the app in either way:
   - set the environment variable `ANTLANTISAFK_CLIENT_ID` (recommended), or
   - put it in `%APPDATA%\AntlantisAFK\config.toml` as
     `azure_client_id = "your-guid-here"` (see `config.example.toml`).

## Running from source

```bat
cd AntlantisAFK
py -3 main.py
```

Optional debug logging to file:

```bat
set ANTLANTISAFK_DEBUG=1
py -3 main.py
```

## Building the standalone .exe

```bat
cd AntlantisAFK
py -3 -m pip install -r requirements-dev.txt
cd antlantisafk\minecraft\worker && npm install && cd ..\..\..
py -3 build.py
```

Result: `dist\AtlantisAFK.exe` (~120 MB) — a **fully self-contained** build:
wave icon, PySide6 GUI, a bundled Node.js runtime, and the
`minecraft-protocol` worker all inside one file. End users need nothing but
the exe. Use `py -3 build.py --no-runtime` for a smaller exe that requires
Node.js on the user's PC.

## How to use the app

1. **Login with Microsoft** — a dialog shows a code such as `ABCD-EFGH` and
   a link (`https://www.microsoft.com/link`). Open the link in a browser,
   enter the code, and sign in with the Microsoft account that owns
   Minecraft: Java Edition. AntlantisAFK never sees your password.
2. Enter the **server address**, **port**, and optionally a specific
   **Minecraft version** (leave `auto` to negotiate).
3. Click **Start AFK**. The status becomes *Connected*; uptime counts up and
   reconnects are tracked. If the connection drops, the app reconnects with
   exponential backoff (5 s → 10 s → 20 s … capped at 10 min) until
   `max_reconnect_attempts` is reached (0 = never give up).
4. **Stop** disconnects. **Logout / Delete Credentials** wipes the stored
   refresh token from Windows Credential Manager — you will have to sign in
   again next time.
5. Minimize-to-tray: enable it in Settings; the tray menu offers Show/Hide,
   Start/Stop AFK, and Exit. Double-click the tray icon to toggle the window.
6. Launching a second instance simply focuses the first one's window.

### Where is my data?

| Data | Location |
|---|---|
| Config | `%APPDATA%\AntlantisAFK\config.toml` |
| Logs | `%APPDATA%\AntlantisAFK\logs\antlantisafk.log` (5 MB × 3 backups) |
| Refresh token | Windows Credential Manager (`AntlantisAFK`) or DPAPI-encrypted blob in `%APPDATA%\AntlantisAFK` |

The config file never contains tokens. Tokens are never logged. The token
travels to the worker only over its stdin pipe, never via command line.

## Troubleshooting

| Problem | Fix |
|---|---|
| "Invalid app registration" (HTTP 403) at the Minecraft step | Mojang's AppID allow-list review is pending ([policy](https://aka.ms/AppRegInfo), submit [here](https://aka.ms/mce-reviewappid)). Everything before it works; retry after approval. |
| "No Azure application (client) ID configured" | Do **Setup: Azure app registration** above. |
| Device code rejected / loop | Make sure "Allow public client flows" = Yes on your Azure app, and you are signing in with a **personal** Microsoft account that owns Java Edition. |
| "This Microsoft account has no Xbox profile" | Sign in once at <https://www.xbox.com> with that account, then retry. |
| Child-account / age errors | Xbox family/age settings block multiplayer; an adult must adjust family settings. |
| "Node.js was not found" | Install Node.js LTS, or set `ANTLANTISAFK_NODE` to your `node.exe`. |
| "The 'minecraft-protocol' npm package is missing" | In `antlantisafk\minecraft\worker`, run `npm install minecraft-protocol`. |
| Instantly kicked / "Failed to verify username" | Wrong version: set `minecraft_version` to the server's version instead of `auto`, and confirm the account owns Java Edition. |
| Token expired, asks to log in again | Normal after long inactivity; sign in once more. |
| Cannot write config | Check `%APPDATA%\AntlantisAFK` permissions; antivirus/controlled-folder access may block writes. |

## Development

```bat
py -3 -m pip install -r requirements-dev.txt
py -3 -m pytest tests/
```

The tests cover config round-trips, validation, the token-store abstraction,
and reconnect logic (with a fake worker). They never touch the network and
never use real credentials.

## Manual test checklist

**Authentication**

- [ ] First run shows "Login with Microsoft"; dialog shows a device code and
      link; browser sign-in completes; username appears in the Account card.
- [ ] Closing the login dialog mid-poll does not crash the app.
- [ ] Restarting the app silently restores the session (username shown
      without prompting).
- [ ] "Logout / Delete Credentials" removes the entry from Windows
      Credential Manager (`Control Panel → Credential Manager → Windows
      Credentials`); next launch requires interactive login.
- [ ] Entering a wrong/expired device code shows a friendly error.

**Connection**

- [ ] Valid server → status *Connected*, uptime increments, player appears
      on the server tab list.
- [ ] Server stop/restart → *Reconnecting…* with growing delays, then
      *Connected* again once the server returns.
- [ ] Unreachable address → reconnect attempts grow to the cap; after
      `max_reconnect_attempts` the app stops with an error status.
- [ ] Bad address/port in the GUI → validation message, no connection.
- [ ] While connected: player stands still in-game; no chat from the app;
      no movement — verify with another account.
- [ ] Kick (e.g. `/kick <name>`) → app reconnects automatically (if allowed).
- [ ] Stop button → status *Disconnected*; tray Start/Stop mirrors the GUI.

**Tray / single instance**

- [ ] Minimize-to-tray on close; tray "Exit" fully quits (worker process
      gone from Task Manager).
- [ ] Second launch focuses the first window and exits.

**Logs**

- [ ] `%APPDATA%\AntlantisAFK\logs\antlantisafk.log` contains connection
      events and auth stages; no token-like strings appear.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

MIT — see [LICENSE](LICENSE).
