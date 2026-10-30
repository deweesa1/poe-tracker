"""GGG API (OAuth 2.1, public client with PKCE). OFF by default.

GGG is not accepting new developer applications at the moment, so this is
a ready-to-finish starting point and has never run against the live API.
When you get a client id:
  1. put it in settings.yaml under api: client_id / contact_email, enabled: true
  2. run:  python -m poetracker.ggg login
  3. run:  python -m poetracker.ggg characters
Tokens are kept in memory only in this draft; storing them (e.g. with the
"keyring" package) is the next step.
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import secrets
import threading
import urllib.parse
import urllib.request
import webbrowser

from .. import __version__

AUTH_URL = "https://www.pathofexile.com/oauth/authorize"
TOKEN_URL = "https://www.pathofexile.com/oauth/token"
API = "https://api.pathofexile.com"
REDIRECT = "http://127.0.0.1:52888/callback"
SCOPES = "account:profile account:characters account:stashes account:leagues"


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


class Client:
    def __init__(self, client_id: str, contact_email: str):
        if not client_id:
            raise ValueError("No client_id: GGG API access isn't set up (see settings.yaml, api:)")
        self.client_id = client_id
        self.user_agent = f"OAuth {client_id}/{__version__} (contact: {contact_email})"
        self.token: dict | None = None

    def login(self, timeout: int = 300) -> dict:
        verifier, challenge = _pkce()
        state = secrets.token_urlsafe(16)
        got: dict = {}

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
                got.update(q)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"PoE Tracker: you can close this tab.")

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 52888), H)
        t = threading.Thread(target=srv.handle_request, daemon=True)
        t.start()
        webbrowser.open(AUTH_URL + "?" + urllib.parse.urlencode({
            "client_id": self.client_id, "response_type": "code", "scope": SCOPES, "state": state,
            "redirect_uri": REDIRECT, "code_challenge": challenge, "code_challenge_method": "S256",
        }))
        t.join(timeout)
        srv.server_close()
        if got.get("state") != state or "code" not in got:
            raise RuntimeError(f"Login failed or was cancelled: {got.get('error', 'no code')}")
        self.token = self._post(TOKEN_URL, {
            "client_id": self.client_id, "grant_type": "authorization_code", "code": got["code"],
            "redirect_uri": REDIRECT, "scope": SCOPES, "code_verifier": verifier,
        })
        return self.token

    def _post(self, url: str, data: dict) -> dict:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(),
                                     headers={"User-Agent": self.user_agent,
                                              "Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())

    def get(self, path: str) -> dict:
        if not self.token:
            raise RuntimeError("Not logged in")
        req = urllib.request.Request(API + path, headers={
            "User-Agent": self.user_agent, "Authorization": f"Bearer {self.token['access_token']}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())

    def characters(self) -> dict:
        return self.get("/character")

    def stashes(self, league: str) -> dict:
        return self.get("/stash/" + urllib.parse.quote(league))
