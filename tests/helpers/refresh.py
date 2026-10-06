"""Token refresh helpers for MS365 testing."""

import json
import time

from ..const import ENTITY_NAME, TOKEN_LOCATION
from ..integration.const_integration import DOMAIN

LOGIN_URL = "https://login.microsoftonline.com/common"


def token_file(tmp_path):
    """Return the path of the token file."""
    return tmp_path / TOKEN_LOCATION / f"{DOMAIN}_{ENTITY_NAME}.token"


def read_token_file(tmp_path):
    """Read the token file."""
    return json.loads(token_file(tmp_path).read_text(encoding="utf8"))


def set_access_token(tmp_path, secret, expires_on):
    """Change the access token in the token file."""
    token = read_token_file(tmp_path)
    for access_token in token["AccessToken"].values():
        access_token["secret"] = secret
        access_token["expires_on"] = str(expires_on)
    token_file(tmp_path).write_text(json.dumps(token), encoding="utf8")


def expire_access_token(tmp_path):
    """Make the access token in the token file an expired one."""
    set_access_token(tmp_path, "fakeaccesstoken", int(time.time()) - 600)


def mock_refresh_failure(requests_mock, error, status_code=400):
    """Make the login service refuse to refresh the token."""
    requests_mock.post(
        f"{LOGIN_URL}/oauth2/v2.0/token",
        status_code=status_code,
        json={"error": error, "error_description": f"AADSTS00000: {error}"},
    )
    # After a failed refresh MSAL looks up the other names of the login service
    requests_mock.get(
        f"{LOGIN_URL}/discovery/instance",
        json={
            "api-version": "1.1",
            "metadata": [
                {
                    "preferred_network": "login.microsoftonline.com",
                    "preferred_cache": "login.windows.net",
                    "aliases": [
                        "login.microsoftonline.com",
                        "login.windows.net",
                        "login.microsoft.com",
                        "sts.windows.net",
                    ],
                }
            ],
        },
    )
