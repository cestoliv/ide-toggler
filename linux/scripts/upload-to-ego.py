#!/usr/bin/env python3
"""Upload a packaged GNOME Shell extension to extensions.gnome.org (EGO).

Uses EGO's official REST API (the same one the website's upload page calls):

  1. POST /api/v1/accounts/login/  {login, password}  -> Knox auth token
  2. POST /api/v1/extensions       multipart: source (.zip),
       shell_license_compliant=true, tos_compliant=true
       with header  Authorization: Token <token>

Token auth is CSRF-exempt, so no session/CSRF dance is needed. Standard library
only (urllib) — no third-party dependencies to install or break.

Credentials come from the EGO_USERNAME / EGO_PASSWORD environment variables.
EGO_USERNAME must be the account *username*, not the email address.

Usage:  upload-to-ego.py <path-to.shell-extension.zip>
"""

import json
import os
import sys
import urllib.error
import urllib.request

BASE = "https://extensions.gnome.org"
LOGIN_URL = f"{BASE}/api/v1/accounts/login/"
UPLOAD_URL = f"{BASE}/api/v1/extensions"  # no trailing slash (that route is the upload view)


def fail(msg):
    print(f"::error::{msg}")
    sys.exit(1)


def extract_token(node):
    """Pull the token string out of the login response, tolerating nesting
    (rest_registration may wrap the Knox token as {"token": {"token": ...}})."""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        for key in ("token", "key", "auth_token", "access"):
            if key in node:
                found = extract_token(node[key])
                if found:
                    return found
    return None


def login(username, password):
    body = json.dumps({"login": username, "password": password}).encode()
    req = urllib.request.Request(
        LOGIN_URL,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        fail(f"Login failed (HTTP {e.code}). Check EGO_USERNAME is your *username* "
             f"(not email) and EGO_PASSWORD is correct.\nResponse: {detail}")
    except urllib.error.URLError as e:
        fail(f"Could not reach {LOGIN_URL}: {e.reason}")

    token = extract_token(data.get("token", data))
    if not token:
        fail(f"Login succeeded but no token found in response: {json.dumps(data)[:500]}")
    print("Logged in to extensions.gnome.org.")
    return token


def build_multipart(zip_path):
    boundary = "----egoupload7f3a9b2c1d8e4f60"
    filename = os.path.basename(zip_path)
    with open(zip_path, "rb") as f:
        file_bytes = f.read()

    def text_field(name, value):
        return (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode()

    body = b""
    body += text_field("shell_license_compliant", "true")
    body += text_field("tos_compliant", "true")
    body += (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="source"; filename="{filename}"\r\n'
        f"Content-Type: application/zip\r\n\r\n"
    ).encode()
    body += file_bytes + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def upload(token, zip_path):
    body, content_type = build_multipart(zip_path)
    req = urllib.request.Request(
        UPLOAD_URL,
        data=body,
        headers={
            "Authorization": f"Token {token}",
            "Content-Type": content_type,
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"Upload accepted (HTTP {resp.status}). The new version is now "
                  f"pending manual review on extensions.gnome.org.")
            print(resp.read().decode(errors="replace")[:1000])
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:1000]
        fail(f"Upload failed (HTTP {e.code}).\nResponse: {detail}")
    except urllib.error.URLError as e:
        fail(f"Could not reach {UPLOAD_URL}: {e.reason}")


def main():
    if len(sys.argv) != 2:
        fail("usage: upload-to-ego.py <path-to.shell-extension.zip>")
    zip_path = sys.argv[1]
    if not os.path.isfile(zip_path):
        fail(f"zip not found: {zip_path}")

    username = os.environ.get("EGO_USERNAME", "").strip()
    password = os.environ.get("EGO_PASSWORD", "").strip()
    if not username or not password:
        print("EGO_USERNAME / EGO_PASSWORD not set — skipping extensions.gnome.org upload.")
        return

    token = login(username, password)
    upload(token, zip_path)


if __name__ == "__main__":
    main()
