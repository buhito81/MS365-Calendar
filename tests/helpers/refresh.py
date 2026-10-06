"""Token refresh helpers for MS365 testing."""

from contextlib import contextmanager
import json
import time
from unittest.mock import patch

from portalocker.exceptions import LockException
from requests.exceptions import ReadTimeout

from ..const import ENTITY_NAME, TOKEN_LOCATION
from ..integration.const_integration import DOMAIN

API = "custom_components.ms365_calendar.classes.api"
LOGIN_URL = "https://login.microsoftonline.com/common"
TOKEN_URL = f"{LOGIN_URL}/oauth2/v2.0/token"
# The token cannot be refreshed for now, though nothing is wrong with it
REFRESH_UNAVAILABLE = [
    ("login", "HTTP Error: 503"),
    ("busy", "Refresh token operation failed: temporarily_unavailable"),
    ("locked", "Could not access locked token file after 3"),
]


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
        TOKEN_URL,
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


def mock_refresh_timeout(requests_mock):
    """Make the login service take too long to refresh the token."""
    requests_mock.post(TOKEN_URL, exc=ReadTimeout("Read timed out"))


@contextmanager
def refresh_unavailable(requests_mock, cause):
    """Have the token refresh fail for now, for a cause in REFRESH_UNAVAILABLE."""
    if cause == "locked":
        # Another refresh keeps the token file locked
        with patch(f"{API}.Lock", side_effect=LockException), patch(f"{API}.time"):
            yield
    else:
        # The login service is down, or too busy to refresh the token
        status_code = 503 if cause == "login" else 400
        mock_refresh_failure(requests_mock, "temporarily_unavailable", status_code)
        yield
