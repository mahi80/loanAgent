"""Authentication + role-based authorisation for the Streamlit apps.

AUTH_MODE (env):
  demo (default) - pick one of a few demo identities in the sidebar. POC only:
                   no passwords, but the *role comes from the identity*, so an
                   approver can no longer self-select a higher authority.
  oidc           - real SSO through Streamlit's built-in OIDC (`st.login`):
                   Microsoft Entra ID, Amazon Cognito, Okta, Auth0...
                   Configure `.streamlit/secrets.toml` (see docs/DOCKER.md).
                   The app role comes from a token claim (AUTH_ROLE_CLAIM,
                   default "roles"), mapped to app roles via AUTH_ROLE_MAP.
  none           - no auth (local dev only); everyone gets the lowest role.

Production: put the same OIDC provider in front at the edge (API Gateway /
API Management validates the JWT) and keep this check in the app as defence in depth.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

import streamlit as st


@dataclass(frozen=True)
class Identity:
    username: str
    name: str
    role: str
    method: str  # demo | oidc | none

    @property
    def label(self) -> str:
        return f"{self.name} ({self.role})"


def mode() -> str:
    return os.getenv("AUTH_MODE", "demo").lower()


def _oidc_identity(roles: list[str]) -> Identity | None:
    user = getattr(st, "user", None)
    if user is None or not getattr(user, "is_logged_in", False):
        return None
    claim = os.getenv("AUTH_ROLE_CLAIM", "roles")
    raw = user.get(claim) or []
    raw = raw if isinstance(raw, list) else [raw]
    mapping = json.loads(os.getenv("AUTH_ROLE_MAP", "{}"))  # e.g. {"credit-sco": "Senior Credit Officer"}
    mapped = [mapping.get(r, r) for r in raw if mapping.get(r, r) in roles]
    role = max(mapped, key=roles.index) if mapped else roles[0]  # highest granted role, default viewer
    return Identity(user.get("email") or user.get("sub", "user"), user.get("name", "user"), role, "oidc")


def sign_in(demo_users: list[tuple[str, str, str]], roles: list[str]) -> Identity:
    """Render the sign-in UI in the sidebar and return the current identity.
    demo_users: (username, display name, role). roles: lowest -> highest privilege."""
    m = mode()
    with st.sidebar:
        if m == "oidc":
            ident = _oidc_identity(roles)
            if ident is None:
                st.info("Sign in with your organisation account to continue.")
                if st.button("🔐 Sign in (SSO)", type="primary", use_container_width=True):
                    st.login()
                st.stop()
            st.caption(f"Signed in via SSO: **{ident.label}**")
            if st.button("Sign out"):
                st.logout()
            return ident
        if m == "none":
            st.caption("⚠️ AUTH_MODE=none - local dev only")
            return Identity("anonymous", "Anonymous", roles[0], "none")
        labels = {f"{n} ({r})": (u, n, r) for u, n, r in demo_users}
        pick = st.selectbox("Signed in as (demo identity)", list(labels), key="demo_identity",
                            help="POC placeholder for SSO. Set AUTH_MODE=oidc for Entra ID / Cognito / Okta.")
        u, n, r = labels[pick]
        return Identity(u, n, r, "demo")


def has_role(ident: Identity, roles: list[str], minimum: str) -> bool:
    return roles.index(ident.role) >= roles.index(minimum)


def require(ident: Identity, roles: list[str], minimum: str, action: str) -> bool:
    """Show a friendly message and return False if the identity lacks the role."""
    if has_role(ident, roles, minimum):
        return True
    st.warning(f"🔒 {action} requires the **{minimum}** role or higher. You are signed in as {ident.label}.")
    return False
