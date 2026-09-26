# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] — 2026-09-26

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
