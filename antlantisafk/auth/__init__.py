"""Authentication subpackage for AntlantisAFK.

Flow (official Microsoft OAuth 2.0 device-code only):

1. Microsoft (MSAL) device-code flow → MSA access + refresh token.
2. Xbox Live (XBL) user token via the MSA access token.
3. XSTS token exchange (relying party ``rp://api.minecraftservices.com/``).
4. Minecraft services login → Minecraft access token + profile (UUID/name).

The refresh token is the ONLY credential persisted (secure token store).
Access tokens live in memory for the session. No passwords are ever handled;
no raw session IDs or third-party tokens are ever accepted.
"""

from .exceptions import (
    AuthError,
    MicrosoftAuthError,
    MinecraftAuthError,
    TokenRefreshError,
    XboxAuthError,
)
from .manager import AuthResult, AuthEvent, MinecraftAuthenticator

__all__ = [
    "AuthError",
    "MicrosoftAuthError",
    "XboxAuthError",
    "MinecraftAuthError",
    "TokenRefreshError",
    "AuthResult",
    "AuthEvent",
    "MinecraftAuthenticator",
]
