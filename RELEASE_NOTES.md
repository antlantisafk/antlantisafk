# AtlantisAFK v0.1.0 — first release 🌊

Single-account AFK companion for Minecraft: Java Edition. Keeps **your** account
online on **one** server by answering keep-alives only — no movement, no chat,
no automation of any kind.

## 📦 What's in the download

**`AtlantisAFK.exe`** (~120 MB) — fully standalone:

- PySide6 GUI with the AtlantisAFK wave branding
- Bundled Node.js runtime + `minecraft-protocol` worker — **no Python or Node.js needed**
- Secure refresh-token storage via Windows Credential Manager (DPAPI fallback)

| File | Size | SHA-256 |
|---|---|---|
| `AtlantisAFK.exe` | ~120 MB | `3c3da38f8e1e715d35b1020b307fa43c986a24fc632b463b69d96fb1467e3ad0` |

## 🚀 Quick start

1. Download and run `AtlantisAFK.exe` (Windows 10/11; SmartScreen may ask —
   click *More info → Run anyway*, it's unsigned).
2. **Login with Microsoft** → complete the browser sign-in with the account
   that owns Minecraft: Java Edition.
3. Enter your server address → **Start AFK**.

## ⚠️ Known limitation at release time

Mojang now manually reviews every **new** Microsoft app registration before it
may call the Minecraft login API
([policy](https://aka.ms/AppRegInfo)). The bundled AppID was submitted via the
[official review form](https://aka.ms/mce-reviewappid) and is awaiting
approval — until then the final login step returns
*"Invalid app registration (HTTP 403)"*. Microsoft sign-in, Xbox Live, and XSTS
all work; everything else in the app works today. This resolves itself when
the allow-list review completes (reviews are weekly).

## ✨ Highlights

- Ocean-palette UI with hero banner, live status dot, and stat tiles
- Exponential-backoff auto-reconnect (5 s base, 10 min cap, attempt cap or ∞)
- System tray with Show/Hide, Start/Stop, Exit; minimize-to-tray option
- Single-instance with window-focus handshake
- Rotating file logs (5 MB × 3) with token redaction
- Optional one-time join message (off by default; the app refuses to spam)
- 75 automated tests covering config, validation, token storage, and
  reconnect logic

## 🛡️ Compliance

Authenticates only via the official Microsoft device-code flow for the user's
own account. No session-ID import, no multi-account, no proxy rotation, no
anti-AFK bypass, no gameplay automation. Use only on servers where AFK is
allowed — AFK clients may violate a server's rules.
