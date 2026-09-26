# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.0] — 2026-09-26

### Changed

- **Unified AtlantisAFK branding everywhere**, including the data folder:
  `%APPDATA%\AntlantisAFK` → `%APPDATA%\AtlantisAFK`. Existing installs
  migrate automatically on first launch (config, logs, stored login).
- Environment variables renamed to `ATLANTISAFK_*`; the old
  `ANTLANTISAFK_*` names keep working as aliases.

### UI polish

- Capsule status pills with a soft pulse animation while connecting or
  reconnecting; status-tinted text.
- Cards highlight on hover; log panel gained a Clear button; version chip in
  the footer; pressing Enter in the server field starts the session.

## [0.1.0] — 2026-09-26

### Branding & UI

- Full visual identity from the AtlantisAFK wave logo: exe/window/tray icon,
  wordmark hero banner, ocean-palette design system.
- Complete UI redesign: hero banner with live status, stat tiles
  (uptime/reconnects/next-retry), scrollable layout, styled scrollbars,
  proper button states (Stop disabled until AFK is running).
- Login dialog retitled to "Sign in to AtlantisAFK".

### Packaging

- **Fully standalone `AtlantisAFK.exe`** (~120 MB): bundled Node.js runtime
  + worker dependencies + branded assets; end users need only the exe.
- `build.py` assembles the runtime automatically (local Node or official
  download) and falls back to `python -m PyInstaller` for --user installs.

### Fixes

- MSAL reserved-scope rejection (login now requests only `XboxLive.signin`).
- DPAPI `Reserved=None` requirement and `CryptUnprotectData` parameter order.
- Missing `_load_refresh` helper in silent session restore.
- Login-dialog cancel crash (`QObject.disconnect` misuse) with cancelled-flag.
- Config save/load no longer demands a server address; settings persist.
- Built-in Azure client ID; status-pill layout; label transparency.

### Added

- Single-account Microsoft authentication via the **official OAuth 2.0
  device-code flow** (MSAL): device code + verification URL, Xbox Live and
  XSTS exchange, Minecraft services login, silent refresh from the stored
  refresh token.
- Secure refresh-token storage in **Windows Credential Manager** via keyring,
  with a DPAPI-encrypted blob fallback; logout deletes all credentials.
- PySide6 GUI: account/server/status/log/settings cards, login dialog with
  copyable device code, coloured status pills, uptime/reconnect counters.
- System tray icon with Show/Hide, Start/Stop AFK, Exit; minimize-to-tray
  option; single-instance guard with window-focus handshake.
- Minecraft connection via a strictly passive Node.js worker
  (`minecraft-protocol`): token handed over on stdin, keep-alives only —
  no movement, chat, mining, combat, or interaction code paths exist.
- Reconnect state machine with exponential backoff (5 s base, 10 min cap),
  max-attempt enforcement, kick/disconnect handling, per-second snapshots.
- TOML configuration with validation, atomic writes, unknown-key
  preservation, and a secret-hygiene guard that refuses to persist
  token-like keys.
- Rotating file logging (5 MB × 3) with token redaction; INFO+ mirror in the
  GUI log panel.
- Unit tests (70) covering config, validators, token-store abstraction, and
  reconnect logic with a fake worker bridge.
- Build tooling: `build.py` / `build.bat` (PyInstaller one-file windowed),
  `requirements.txt`, `requirements-dev.txt`, `config.example.toml`.
