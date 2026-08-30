from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

try:
    from starlette.requests import Request
    import personal_oauth
except ModuleNotFoundError:
    Request = object  # type: ignore[assignment,misc]
    personal_oauth = None  # type: ignore[assignment]


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _request(method: str, path: str, body: bytes = b"") -> Request:
    delivered = False

    async def receive() -> dict:
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "scheme": "https",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
            "client": ("127.0.0.1", 12345),
            "server": ("mcp.example.test", 443),
        },
        receive,
    )


@unittest.skipUnless(personal_oauth is not None, "remote HTTP dependencies are not installed")
class PersonalOAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        personal_oauth._authorization_codes.clear()
        personal_oauth._failed_logins.clear()
        personal_oauth._used_refresh_tokens.clear()
        self.environment = {
            "KERR_QNM_PUBLIC_BASE_URL": "https://mcp.example.test",
            "KERR_QNM_OAUTH_PASSWORD": "owner-password-that-is-long-and-random",
            "KERR_QNM_OAUTH_SIGNING_SECRET": "signing-secret-that-is-independent-and-long",
        }

    def test_discovery_metadata_is_bound_to_mcp_resource(self) -> None:
        with patch.dict(os.environ, self.environment, clear=False):
            protected = personal_oauth.protected_resource_metadata()
            authorization = personal_oauth.authorization_server_metadata()
        protected_body = json.loads(protected.body)
        authorization_body = json.loads(authorization.body)
        self.assertEqual(protected_body["resource"], "https://mcp.example.test/mcp")
        self.assertEqual(protected_body["authorization_servers"], ["https://mcp.example.test"])
        self.assertTrue(authorization_body["client_id_metadata_document_supported"])
        self.assertIn("S256", authorization_body["code_challenge_methods_supported"])
        self.assertEqual(authorization_body["token_endpoint_auth_methods_supported"], ["none"])

    def test_authorization_code_pkce_and_refresh_flow(self) -> None:
        verifier = "v" * 64
        challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
        authorization_values = {
            "response_type": "code",
            "client_id": personal_oauth.CHATGPT_CLIENT_ID,
            "redirect_uri": personal_oauth.CHATGPT_REDIRECT_URI,
            "state": "state-value",
            "resource": "https://mcp.example.test/mcp",
            "scope": personal_oauth.SCOPE,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "password": self.environment["KERR_QNM_OAUTH_PASSWORD"],
        }
        with patch.dict(os.environ, self.environment, clear=False):
            authorization = asyncio.run(
                personal_oauth.authorize(
                    _request("POST", "/oauth/authorize", urlencode(authorization_values).encode("utf-8"))
                )
            )
            location = authorization.headers["location"]
            query = parse_qs(urlsplit(location).query)
            self.assertEqual(query["state"], ["state-value"])
            self.assertEqual(query["iss"], ["https://mcp.example.test"])

            token_values = {
                "grant_type": "authorization_code",
                "client_id": personal_oauth.CHATGPT_CLIENT_ID,
                "redirect_uri": personal_oauth.CHATGPT_REDIRECT_URI,
                "resource": "https://mcp.example.test/mcp",
                "code": query["code"][0],
                "code_verifier": verifier,
            }
            token_response = asyncio.run(
                personal_oauth.token(_request("POST", "/oauth/token", urlencode(token_values).encode("utf-8")))
            )
            token_body = json.loads(token_response.body)
            self.assertEqual(token_body["token_type"], "Bearer")
            self.assertTrue(personal_oauth.validate_access_token(token_body["access_token"]))

            refresh_values = {
                "grant_type": "refresh_token",
                "client_id": personal_oauth.CHATGPT_CLIENT_ID,
                "resource": "https://mcp.example.test/mcp",
                "refresh_token": token_body["refresh_token"],
            }
            refresh_response = asyncio.run(
                personal_oauth.token(_request("POST", "/oauth/token", urlencode(refresh_values).encode("utf-8")))
            )
            refreshed = json.loads(refresh_response.body)
            self.assertTrue(personal_oauth.validate_access_token(refreshed["access_token"]))
            self.assertNotEqual(refreshed["refresh_token"], token_body["refresh_token"])
            replay_response = asyncio.run(
                personal_oauth.token(_request("POST", "/oauth/token", urlencode(refresh_values).encode("utf-8")))
            )
            self.assertEqual(json.loads(replay_response.body)["error"], "invalid_grant")

    def test_wrong_resource_is_rejected(self) -> None:
        values = {
            "grant_type": "authorization_code",
            "client_id": personal_oauth.CHATGPT_CLIENT_ID,
            "resource": "https://attacker.example/mcp",
        }
        with patch.dict(os.environ, self.environment, clear=False):
            response = asyncio.run(personal_oauth.token(_request("POST", "/oauth/token", urlencode(values).encode("utf-8"))))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.body)["error"], "invalid_target")
