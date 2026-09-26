"""AtlantisAFK — a personal, single-account AFK companion for Minecraft: Java Edition.

This application keeps ONE user-owned Microsoft/Minecraft account connected to
ONE Minecraft server, responding only to keep-alive packets. It performs no
gameplay automation whatsoever.

Strict compliance rules (see README.md "Legal & Safety"):
- Authentication ONLY via the official Microsoft OAuth 2.0 device-code flow.
- No raw session IDs, no third-party tokens, no Microsoft passwords, ever.
- No movement, chat, mining, combat, item use, or entity interaction.
- No anti-AFK bypass of any kind.
"""

from __future__ import annotations

APP_NAME: str = "AtlantisAFK"          # display name (user-visible)
APP_ID: str = "AtlantisAFK"            # stable internal id (paths, storage)
APP_VERSION: str = "0.2.0"
APP_AUTHOR: str = "AtlantisAFK contributors"
APP_DESCRIPTION: str = "Single-account AFK companion for Minecraft: Java Edition"

__all__ = ["APP_NAME", "APP_ID", "APP_VERSION", "APP_AUTHOR", "APP_DESCRIPTION"]
