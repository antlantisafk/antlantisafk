"""Authentication orchestration for AntlantisAFK.

Implements the complete official chain for a user's OWN account:

1. **Microsoft device-code flow** (MSAL, authority ``consumers``):
   the user visits microsoft.com/link and enters the displayed code. The app
   never sees a password.
2. **Xbox Live (XBL)** user token exchange.
3. **XSTS** token exchange (relying party ``rp://api.minecraftservices.com/``).
4. **Minecraft services** login → Minecraft access token + profile UUID/name.

Only the Microsoft refresh token is persisted (secure token store). Access
tokens are held in memory for the session. Errors are reported with
user-friendly messages; tokens are never logged.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import requests

from ..logging_setup import REDACTED
from ..security.token_store import TokenStore, TokenStoreError
from .exceptions import (
    MinecraftAuthError,
    MicrosoftAuthError,
    TokenRefreshError,
    XboxAuthError,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Endpoints (official Microsoft / Xbox / Minecraft services only)
# ---------------------------------------------------------------------------

MSA_AUTHORITY: str = "https://login.microsoftonline.com/consumers"
XBL_USER_AUTH_URL: str = "https://user.auth.xboxlive.com/user/authenticate"
XSTS_AUTH_URL: str = "https://xsts.auth.xboxlive.com/xsts/authorize"
MC_LOGIN_URL: str = "https://api.minecraftservices.com/authentication/login_with_xbox"
MC_PROFILE_URL: str = "https://api.minecraftservices.com/minecraft/profile"

#: OAuth scopes for the device-code flow. IMPORTANT: request ONLY
#: "XboxLive.signin" — MSAL automatically adds the reserved scopes
#: (offline_access, openid, profile) and raises
#: "You cannot use any scope value that is reserved" if they are passed
#: explicitly. The refresh token is still issued because MSAL requests
#: offline_access itself.
MSA_SCOPES: list[str] = ["XboxLive.signin"]

REQUEST_TIMEOUT: float = 20.0

#: Runs of 24+ token-like characters in error strings are redacted.
_LONG_BLOB_RE: re.Pattern[str] = re.compile(r"[A-Za-z0-9._\-]{24,}")

# Friendly messages for well-known XSTS denial codes.
_XSTS_ERR_MESSAGES: dict[int, str] = {
    2148916233: "This Microsoft account has no Xbox profile. Sign up at "
                "xbox.com with this account first, then try again.",
    2148916234: "The account's country does not allow Xbox access.",
    2148916236: "Adult verification is required for this account (age "
                "verification needed on xbox.com).",
    2148916237: "Adult verification is required for this account (age "
                "verification needed on xbox.com).",
    2148916238: "This is a child account and cannot access Minecraft "
                "multiplayer until an adult adds it to a family group.",
}


def _sanitize(text: str) -> str:
    """Redact token-like blobs from an error message before display/log."""
    if not text:
        return ""
    return _LONG_BLOB_RE.sub(REDACTED, text)


@dataclass
class AuthEvent:
    """Progress event emitted during the device-code login flow.

    Attributes:
        stage: Machine-readable stage name (e.g. ``"device_code"``,
            ``"xbl"``, ``"xsts"``, ``"minecraft"``, ``"done"``).
        message: Human-readable progress text for the GUI/log.
        verification_url: URL the user must visit (device flow only).
        user_code: Code the user must enter (device flow only).
        expires_in: Seconds until the device code expires.
    """

    stage: str
    message: str
    verification_url: str | None = None
    user_code: str | None = None
    expires_in: int | None = None


@dataclass
class AuthResult:
    """Successful authentication outcome.

    The Minecraft access token is intentionally excluded from ``repr`` so it
    can never leak into logs or exception text.
    """

    username: str
    uuid: str  # no dashes; format used by the Minecraft join protocol
    access_token: str = field(repr=False)
    expires_at: float
    xuid: str | None = None

    def token_expired(self, skew_seconds: float = 60.0) -> bool:
        """True when the Minecraft token is expired (with safety skew)."""
        return time.time() >= (self.expires_at - skew_seconds)


class MinecraftAuthenticator:
    """One-account Microsoft device-code authenticator for Minecraft Java.

    Args:
        token_store: Secure storage for the refresh token.
        client_id: Azure AD application (client) ID. May be empty if the
            caller passes it later via :attr:`client_id`, but a login cannot
            start without it.
    """

    def __init__(self, token_store: TokenStore, client_id: str = "") -> None:
        self.token_store = token_store
        self.client_id = client_id
        self._http = requests.Session()
        self._http.headers.update({"Accept": "application/json"})
        self._last_result: AuthResult | None = None

    # ------------------------------------------------------------------
    # Interactive login (device code)
    # ------------------------------------------------------------------

    def start_device_login(
        self,
        on_event: Callable[[AuthEvent], None] | None = None,
    ) -> AuthResult:
        """Run the full interactive login chain and return the profile.

        Args:
            on_event: Optional callback receiving :class:`AuthEvent` progress
                updates (device code display, stage transitions).

        Raises:
            MicrosoftAuthError: Device flow failed or timed out.
            XboxAuthError: XBL/XSTS exchange failed.
            MinecraftAuthError: Minecraft services login/profile failed.
        """
        if not self.client_id:
            raise MicrosoftAuthError(
                "No Azure application (client) ID configured. Set it in the "
                "config file (azure_client_id) or the ANTLANTISAFK_CLIENT_ID "
                "environment variable. See README 'Setup'."
            )

        msa_access, msa_refresh = self._msal_device_flow(on_event)

        try:
            self.token_store.save_refresh_token(msa_refresh)
        except TokenStoreError as exc:
            # Still usable for this session; warn loudly.
            logger.error("Could not persist refresh token: %s", exc)

        xbl_token, uhs = self._xbl_auth(msa_access, on_event)
        xsts_token, uhs = self._xsts_auth(xbl_token, uhs, on_event)
        result = self._minecraft_login(xsts_token, uhs, on_event)

        self._last_result = result
        if on_event:
            on_event(AuthEvent("done", f"Logged in as {result.username}"))
        return result

    # ------------------------------------------------------------------
    # Silent session restore
    # ------------------------------------------------------------------

    def _load_refresh(self) -> str | None:
        """Read the stored refresh token, returning None on any problem."""
        try:
            return self.token_store.load_refresh_token()
        except TokenStoreError as exc:
            logger.error("Could not read stored refresh token: %s", exc)
            return None

    def restore_session(self) -> AuthResult | None:
        """Silently renew the session from the stored refresh token.

        Returns:
            A fresh :class:`AuthResult`, or ``None`` if no token is stored.

        Raises:
            TokenRefreshError: The stored token was rejected; interactive
                login is required again.
        """
        refresh = self._load_refresh()
        if refresh is None:
            return None
        msa_access, msa_refresh = self._msal_refresh(refresh)
        if msa_refresh and msa_refresh != refresh:
            try:
                self.token_store.save_refresh_token(msa_refresh)
            except TokenStoreError as exc:
                logger.error("Could not persist rotated refresh token: %s", exc)
        xbl_token, uhs = self._xbl_auth(msa_access)
        xsts_token, uhs = self._xsts_auth(xbl_token, uhs)
        result = self._minecraft_login(xsts_token, uhs)
        self._last_result = result
        return result

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    def logout(self) -> None:
        """Delete ALL stored credentials and forget the in-memory session.

        Per the security requirements this clears the refresh token from the
        system credential manager (or DPAPI blob) and any cached state.
        """
        self._last_result = None
        try:
            self.token_store.delete_credentials()
            logger.info("All stored credentials deleted (logout).")
        except TokenStoreError as exc:
            logger.error("Logout could not delete credentials: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Microsoft device flow (MSAL)
    # ------------------------------------------------------------------

    def _msal_device_flow(
        self, on_event: Callable[[AuthEvent], None] | None
    ) -> tuple[str, str]:
        """Run the MSAL device-code flow; return (access, refresh) tokens."""
        try:
            import msal
        except ImportError as exc:  # pragma: no cover
            raise MicrosoftAuthError(
                "The 'msal' package is required for Microsoft login. "
                "Install it with: pip install msal"
            ) from exc

        app = msal.PublicClientApplication(self.client_id, authority=MSA_AUTHORITY)
        flow = app.initiate_device_flow(scopes=MSA_SCOPES)
        if "user_code" not in flow:
            raise MicrosoftAuthError(
                "Could not start device login: "
                + _sanitize(str(flow.get("error_description", flow)))
            )

        if on_event:
            on_event(
                AuthEvent(
                    stage="device_code",
                    message=(
                        f"Visit {flow['verification_uri']} and enter code "
                        f"{flow['user_code']}"
                    ),
                    verification_url=flow["verification_uri"],
                    user_code=flow["user_code"],
                    expires_in=int(flow.get("expires_in", 900)),
                )
            )

        logger.info("Device-code login started (code expires in %ss).",
                    flow.get("expires_in", 900))
        result = app.acquire_token_by_device_flow(flow)  # polls internally

        if "access_token" not in result:
            err = _sanitize(str(result.get("error_description") or result))
            logger.error("Microsoft device flow failed: %s", err)
            raise MicrosoftAuthError(f"Microsoft login failed: {err}")

        access = result["access_token"]
        refresh = result.get("refresh_token")
        if not refresh:
            raise MicrosoftAuthError(
                "Microsoft did not return a refresh token (offline_access "
                "scope missing?). Please try logging in again."
            )
        logger.info("Microsoft device flow succeeded.")
        return access, refresh

    def _msal_refresh(self, refresh_token: str) -> tuple[str, str | None]:
        """Exchange a refresh token for a new access token silently."""
        try:
            import msal
        except ImportError as exc:  # pragma: no cover
            raise TokenRefreshError(
                "The 'msal' package is required. Install it with: pip install msal"
            ) from exc

        app = msal.PublicClientApplication(self.client_id, authority=MSA_AUTHORITY)
        result = app.acquire_token_by_refresh_token(
            refresh_token, scopes=MSA_SCOPES
        )
        if "access_token" not in result:
            err = _sanitize(str(result.get("error_description") or result))
            logger.error("Silent token refresh failed: %s", err)
            raise TokenRefreshError(
                "Session expired — please log in with Microsoft again."
            )
        logger.info("Silent token refresh succeeded.")
        return result["access_token"], result.get("refresh_token")

    # ------------------------------------------------------------------
    # Xbox Live + XSTS
    # ------------------------------------------------------------------

    def _xbl_auth(
        self, msa_access_token: str,
        on_event: Callable[[AuthEvent], None] | None = None,
    ) -> tuple[str, str]:
        """Exchange the MSA token for an Xbox Live (XBL) token + user hash."""
        if on_event:
            on_event(AuthEvent("xbl", "Authenticating with Xbox Live…"))
        payload = {
            "Properties": {
                "AuthMethod": "RPS",
                "SiteName": "user.auth.xboxlive.com",
                "RpsTicket": f"d={msa_access_token}",
            },
            "RelyingParty": "http://auth.xboxlive.com",
            "TokenType": "JWT",
        }
        data = self._post_json(XBL_USER_AUTH_URL, payload, XboxAuthError)
        token = data.get("Token")
        uhs = (data.get("DisplayClaims", {}).get("xui") or [{}])[0].get("uhs")
        if not token or not uhs:
            raise XboxAuthError(
                "Xbox Live authentication returned an unexpected response."
            )
        logger.info("Xbox Live authentication succeeded.")
        return token, uhs

    def _xsts_auth(
        self, xbl_token: str, uhs: str,
        on_event: Callable[[AuthEvent], None] | None = None,
    ) -> tuple[str, str]:
        """Exchange the XBL token for an XSTS token (Minecraft relying party)."""
        if on_event:
            on_event(AuthEvent("xsts", "Requesting Xbox security token (XSTS)…"))
        payload = {
            "Properties": {
                "SandboxId": "RETAIL",
                "UserTokens": [xbl_token],
            },
            "RelyingParty": "rp://api.minecraftservices.com/",
            "TokenType": "JWT",
        }
        try:
            data = self._post_json(XSTS_AUTH_URL, payload, XboxAuthError)
        except XboxAuthError as exc:
            # XSTS denials arrive as HTTP 401 with an XErr code in the body;
            # _post_json embeds the body in the message — map known codes.
            m = re.search(r"2148916\d{3}", str(exc))
            if m:
                xerr = int(m.group(0))
                friendly = _XSTS_ERR_MESSAGES.get(xerr)
                if friendly:
                    raise XboxAuthError(friendly) from exc
            raise
        token = data.get("Token")
        new_uhs = (data.get("DisplayClaims", {}).get("xui") or [{}])[0].get(
            "uhs", uhs
        )
        if not token:
            raise XboxAuthError(
                "XSTS token exchange returned an unexpected response."
            )
        logger.info("XSTS token exchange succeeded.")
        return token, new_uhs

    # ------------------------------------------------------------------
    # Minecraft services
    # ------------------------------------------------------------------

    def _minecraft_login(
        self, xsts_token: str, uhs: str,
        on_event: Callable[[AuthEvent], None] | None = None,
    ) -> AuthResult:
        """Log in to Minecraft services and fetch the profile."""
        if on_event:
            on_event(AuthEvent("minecraft", "Signing in to Minecraft…"))
        identity = f"XBL3.0 x={uhs};{xsts_token}"
        data = self._post_json(MC_LOGIN_URL, {"identityToken": identity},
                               MinecraftAuthError)
        mc_token = data.get("access_token")
        expires_in = data.get("expires_in", 86400)
        if not mc_token:
            raise MinecraftAuthError(
                "Minecraft login did not return an access token. Does this "
                "account own Minecraft: Java Edition?"
            )

        profile = self._get_json(
            MC_PROFILE_URL,
            headers={"Authorization": f"Bearer {mc_token}"},
            err_cls=MinecraftAuthError,
        )
        username = profile.get("name")
        uuid = profile.get("id")
        if not username or not uuid:
            raise MinecraftAuthError(
                "Could not fetch the Minecraft profile. Does this account "
                "own Minecraft: Java Edition?"
            )

        result = AuthResult(
            username=str(username),
            uuid=str(uuid).replace("-", ""),
            access_token=str(mc_token),
            expires_at=time.time() + float(expires_in),
            xuid=data.get("username"),  # MC login returns the XUID here
        )
        logger.info("Minecraft authentication succeeded for %s.", result.username)
        return result

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _post_json(self, url: str, payload: dict[str, Any],
                   err_cls: type[Exception]) -> dict[str, Any]:
        """POST JSON and parse the JSON response with clean error mapping."""
        try:
            resp = self._http.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            logger.error("Network error contacting %s: %s", url, exc)
            raise err_cls(
                f"Network error while authenticating (is your internet "
                f"connection working?): {exc.__class__.__name__}"
            ) from exc
        return self._handle_response(resp, url, err_cls)

    def _get_json(self, url: str, headers: dict[str, str],
                  err_cls: type[Exception]) -> dict[str, Any]:
        """GET JSON with clean error mapping."""
        try:
            resp = self._http.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            logger.error("Network error contacting %s: %s", url, exc)
            raise err_cls(
                f"Network error while authenticating: {exc.__class__.__name__}"
            ) from exc
        return self._handle_response(resp, url, err_cls)

    @staticmethod
    def _handle_response(resp: requests.Response, url: str,
                         err_cls: type[Exception]) -> dict[str, Any]:
        """Raise a typed, sanitised, user-friendly error on non-2xx."""
        if resp.status_code // 100 == 2:
            try:
                return resp.json()
            except ValueError as exc:
                raise err_cls(
                    f"Unexpected (non-JSON) response from authentication server."
                ) from exc

        # Try to extract a useful, sanitised reason from the body.
        detail = ""
        try:
            body = resp.json()
            detail = str(body.get("error_description") or body.get("detail")
                         or body.get("errorMessage") or body)
        except ValueError:
            detail = resp.text[:200] if resp.text else ""
        detail = _sanitize(detail)
        logger.error("Auth request to %s failed: HTTP %s (%s)", url,
                     resp.status_code, detail)
        raise err_cls(
            f"Authentication request failed (HTTP {resp.status_code}). {detail}"
        )
