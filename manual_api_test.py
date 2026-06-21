# -*- coding: utf-8 -*-

# Kiro Gateway
# https://github.com/jwadow/kiro-gateway
# Copyright (C) 2025 Jwadow
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

import json
import os
import sqlite3
import sys
import uuid
from pathlib import Path
from enum import Enum

import httpx
from dotenv import load_dotenv
from loguru import logger

# --- Load environment variables ---
load_dotenv()


class AuthType(Enum):
    """Type of authentication mechanism."""
    KIRO_DESKTOP = "kiro_desktop"
    AWS_SSO_OIDC = "aws_sso_oidc"


# --- Configuration ---
# API region - CodeWhisperer API is only available in us-east-1
API_REGION = "us-east-1"
KIRO_API_HOST = f"https://q.{API_REGION}.amazonaws.com"
KIRO_DESKTOP_TOKEN_URL = f"https://prod.{API_REGION}.auth.desktop.kiro.dev/refreshToken"

# SSO region - may differ from API region (e.g., ap-southeast-1 for Singapore users)
# This is used only for AWS SSO OIDC token refresh
SSO_REGION = None
AWS_SSO_OIDC_TOKEN_URL = None  # Will be set when SSO_REGION is known

REFRESH_TOKEN = os.getenv("REFRESH_TOKEN")
PROFILE_ARN = os.getenv("PROFILE_ARN", "arn:aws:codewhisperer:us-east-1:699475941385:profile/EHGA3GRVQMUK")
KIRO_CLI_DB_FILE = os.getenv("KIRO_CLI_DB_FILE", "")
KIRO_CLI_DB_FILE = os.getenv("KIRO_CLI_DB_FILE", "")

# AWS SSO OIDC specific credentials
CLIENT_ID = None
CLIENT_SECRET = None
SCOPES = None
AUTH_TOKEN = None
AUTH_TYPE = AuthType.KIRO_DESKTOP


def load_credentials_from_json(file_path: str) -> bool:
    """Load credentials from JSON file."""
    global REFRESH_TOKEN, PROFILE_ARN, CLIENT_ID, CLIENT_SECRET, AUTH_TYPE
    global SSO_REGION, AWS_SSO_OIDC_TOKEN_URL
    
    try:
        creds_path = Path(file_path).expanduser()
        if not creds_path.exists():
            logger.warning(f"Credentials file not found: {file_path}")
            return False
        
        with open(creds_path, 'r', encoding='utf-8') as f:
            creds_data = json.load(f)
        
        # Load common fields
        if 'refreshToken' in creds_data:
            REFRESH_TOKEN = creds_data['refreshToken']
        if 'profileArn' in creds_data:
            PROFILE_ARN = creds_data['profileArn']
        if 'region' in creds_data:
            # Store as SSO region for OIDC token refresh only
            # IMPORTANT: CodeWhisperer API is only available in us-east-1,
            # so we don't update KIRO_API_HOST here
            SSO_REGION = creds_data['region']
            AWS_SSO_OIDC_TOKEN_URL = f"https://oidc.{SSO_REGION}.amazonaws.com/token"
            logger.debug(f"SSO region from JSON: {SSO_REGION} (API stays at {API_REGION})")
        
        # Load AWS SSO OIDC specific fields
        if 'clientId' in creds_data:
            CLIENT_ID = creds_data['clientId']
        if 'clientSecret' in creds_data:
            CLIENT_SECRET = creds_data['clientSecret']
        
        # Detect auth type
        if CLIENT_ID and CLIENT_SECRET:
            AUTH_TYPE = AuthType.AWS_SSO_OIDC
            logger.info(f"Detected auth type: AWS SSO OIDC")
        else:
            AUTH_TYPE = AuthType.KIRO_DESKTOP
            logger.info(f"Detected auth type: Kiro Desktop")
        
        logger.info(f"Credentials loaded from {file_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error loading credentials from file: {e}")
        return False


def load_credentials_from_sqlite(db_path: str) -> bool:
    """Load credentials from kiro-cli SQLite database."""
    global REFRESH_TOKEN, CLIENT_ID, CLIENT_SECRET, AUTH_TYPE, SCOPES, AUTH_TOKEN
    global SSO_REGION, AWS_SSO_OIDC_TOKEN_URL
    
    try:
        path = Path(db_path).expanduser()
        if not path.exists():
            logger.warning(f"SQLite database not found: {db_path}")
            return False
        
        conn = sqlite3.connect(str(path))
        cursor = conn.cursor()
        
        # Load token data (try both kiro-cli and codewhisperer key formats)
        cursor.execute("SELECT value FROM auth_kv WHERE key = ?", ("kirocli:odic:token",))
        token_row = cursor.fetchone()
        if not token_row:
            cursor.execute("SELECT value FROM auth_kv WHERE key = ?", ("codewhisperer:odic:token",))
            token_row = cursor.fetchone()
        
        if token_row:
            token_data = json.loads(token_row[0])
            if token_data:
                # Check if we have a valid access token
                if 'access_token' in token_data and 'expires_at' in token_data:
                    from datetime import datetime
                    expires_at = datetime.fromisoformat(token_data['expires_at'].replace('Z', '+00:00'))
                    if expires_at > datetime.now().astimezone():
                        AUTH_TOKEN = token_data['access_token']
                        logger.info("Found valid access token in database (will use after HEADERS init)")
                if 'refresh_token' in token_data:
                    REFRESH_TOKEN = token_data['refresh_token']
                if 'scopes' in token_data:
                    SCOPES = token_data['scopes']
                if 'region' in token_data:
                    # Store as SSO region for OIDC token refresh only
                    # IMPORTANT: CodeWhisperer API is only available in us-east-1,
                    # so we don't update KIRO_API_HOST here
                    SSO_REGION = token_data['region']
                    AWS_SSO_OIDC_TOKEN_URL = f"https://oidc.{SSO_REGION}.amazonaws.com/token"
                    logger.debug(f"SSO region from SQLite: {SSO_REGION} (API stays at {API_REGION})")
        
        # Load device registration (client_id, client_secret) - try both key formats
        cursor.execute("SELECT value FROM auth_kv WHERE key = ?", ("kirocli:odic:device-registration",))
        registration_row = cursor.fetchone()
        if not registration_row:
            cursor.execute("SELECT value FROM auth_kv WHERE key = ?", ("codewhisperer:odic:device-registration",))
            registration_row = cursor.fetchone()
        
        if registration_row:
            registration_data = json.loads(registration_row[0])
            if registration_data:
                if 'client_id' in registration_data:
                    CLIENT_ID = registration_data['client_id']
                if 'client_secret' in registration_data:
                    CLIENT_SECRET = registration_data['client_secret']
        
        conn.close()
        
        # Detect auth type
        if CLIENT_ID and CLIENT_SECRET:
            AUTH_TYPE = AuthType.AWS_SSO_OIDC
            logger.info(f"Detected auth type: AWS SSO OIDC (from SQLite)")
        else:
            AUTH_TYPE = AuthType.KIRO_DESKTOP
            logger.info(f"Detected auth type: Kiro Desktop (from SQLite)")
        
        logger.info(f"Credentials loaded from SQLite: {db_path}")
        return True
        
    except sqlite3.Error as e:
        logger.error(f"SQLite error: {e}")
        return False
    except Exception as e:
        logger.error(f"Error loading credentials from SQLite: {e}")
        return False


# --- Load credentials (priority: SQLite > JSON > env) ---
cred_source = "REFRESH_TOKEN"

if KIRO_CLI_DB_FILE:
    if load_credentials_from_sqlite(KIRO_CLI_DB_FILE):
        cred_source = "KIRO_CLI_DB_FILE (SQLite)"
elif KIRO_CLI_DB_FILE:
    if load_credentials_from_json(KIRO_CLI_DB_FILE):
        cred_source = "KIRO_CLI_DB_FILE (JSON)"

# --- Validate required credentials ---
if not REFRESH_TOKEN:
    logger.error("No credentials configured. Set REFRESH_TOKEN, KIRO_CLI_DB_FILE, or KIRO_CLI_DB_FILE. Exiting.")
    sys.exit(1)

# Additional validation for AWS SSO OIDC
if AUTH_TYPE == AuthType.AWS_SSO_OIDC and (not CLIENT_ID or not CLIENT_SECRET):
    logger.error("AWS SSO OIDC requires clientId and clientSecret. Exiting.")
    sys.exit(1)

# Global variables
AUTH_TOKEN = None
HEADERS = {
    "Authorization": None,
    "Content-Type": "application/json",
    "User-Agent": "aws-sdk-js/1.0.27 ua/2.1 os/win32#10.0.19044 lang/js md/nodejs#22.21.1 api/codewhispererstreaming#1.0.27 m/E KiroIDE-0.7.45-31c325a0ff0a9c8dec5d13048f4257462d751fe5b8af4cb1088f1fca45856c64",
    "x-amz-user-agent": "aws-sdk-js/1.0.27 KiroIDE-0.7.45-31c325a0ff0a9c8dec5d13048f4257462d751fe5b8af4cb1088f1fca45856c64",
    "x-amzn-codewhisperer-optout": "true",
    "x-amzn-kiro-agent-mode": "vibe",
}


def refresh_auth_token():
    """Refreshes AUTH_TOKEN via appropriate endpoint based on auth type."""
    global AUTH_TOKEN, HEADERS
    
    if AUTH_TYPE == AuthType.AWS_SSO_OIDC:
        return refresh_auth_token_aws_sso_oidc()
    else:
        return refresh_auth_token_kiro_desktop()


def refresh_auth_token_kiro_desktop():
    """Refreshes AUTH_TOKEN via Kiro Desktop Auth endpoint."""
    global AUTH_TOKEN, HEADERS
    logger.info("Refreshing Kiro token via Kiro Desktop Auth...")
    
    payload = {"refreshToken": REFRESH_TOKEN}
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "KiroIDE-0.7.45-31c325a0ff0a9c8dec5d13048f4257462d751fe5b8af4cb1088f1fca45856c64",
    }
    
    try:
        response = httpx.post(KIRO_DESKTOP_TOKEN_URL, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        new_token = data.get("accessToken")
        expires_in = data.get("expiresIn")
        
        if not new_token:
            logger.error("Failed to get accessToken from response")
            return False

        logger.success(f"Token refreshed via Kiro Desktop Auth. Expires in: {expires_in}s")
        AUTH_TOKEN = new_token
        HEADERS['Authorization'] = f"Bearer {AUTH_TOKEN}"
        return True
        
    except httpx.HTTPError as e:
        logger.error(f"Error refreshing token via Kiro Desktop Auth: {e}")
        if hasattr(e, 'response') and e.response:
            logger.error(f"Server response: {e.response.status_code} {e.response.text}")
        return False


def refresh_auth_token_aws_sso_oidc():
    """Refreshes AUTH_TOKEN via AWS SSO OIDC endpoint."""
    global AUTH_TOKEN, HEADERS
    logger.info("Refreshing Kiro token via AWS SSO OIDC...")
    
    # Determine SSO OIDC URL (use SSO_REGION if set, otherwise fall back to API_REGION)
    sso_region = SSO_REGION or API_REGION
    oidc_url = AWS_SSO_OIDC_TOKEN_URL or f"https://oidc.{sso_region}.amazonaws.com/token"
    
    # AWS SSO OIDC uses form-urlencoded data
    data = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
    }
    
    # Note: scope parameter is NOT sent during refresh per OAuth 2.0 RFC 6749 Section 6
    # AWS SSO OIDC uses the originally granted scopes automatically
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }
    
    # Log request details (without secrets) for debugging
    logger.debug(f"AWS SSO OIDC refresh request: url={oidc_url}, "
                 f"sso_region={sso_region}, api_region={API_REGION}, "
                 f"client_id={CLIENT_ID[:8] if CLIENT_ID else 'None'}...")
    
    try:
        response = httpx.post(oidc_url, data=data, headers=headers)
        
        # Log response details for debugging (especially on errors)
        if response.status_code != 200:
            logger.error(f"AWS SSO OIDC refresh failed: status={response.status_code}")
            logger.error(f"AWS SSO OIDC response body: {response.text}")
            # Try to parse AWS error for more details
            try:
                error_json = response.json()
                error_code = error_json.get("error", "unknown")
                error_desc = error_json.get("error_description", "no description")
                logger.error(f"AWS SSO OIDC error details: error={error_code}, "
                             f"description={error_desc}")
            except Exception:
                pass  # Body wasn't JSON, already logged as text
            response.raise_for_status()
        
        result = response.json()
        
        new_token = result.get("accessToken")
        expires_in = result.get("expiresIn", 3600)
        
        if not new_token:
            logger.error(f"Failed to get accessToken from AWS SSO OIDC response: {result}")
            return False

        logger.success(f"Token refreshed via AWS SSO OIDC. Expires in: {expires_in}s")
        AUTH_TOKEN = new_token
        HEADERS['Authorization'] = f"Bearer {AUTH_TOKEN}"
        return True
        
    except httpx.HTTPError as e:
        logger.error(f"Error refreshing token via AWS SSO OIDC: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Server response: {e.response.status_code} {e.response.text}")
        return False


def get_profile_arn():
    """Gets the profile ARN from ListAvailableProfiles endpoint."""
    global PROFILE_ARN
    logger.info("Getting profile ARN from /ListAvailableProfiles...")
    url = f"{KIRO_API_HOST}/ListAvailableProfiles"
    
    try:
        response = httpx.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        
        profiles = data.get("profiles", [])
        if profiles:
            # Use the first available profile
            PROFILE_ARN = profiles[0].get("arn")
            logger.info(f"Found profile ARN: {PROFILE_ARN}")
            return True
        else:
            logger.warning("No profiles found")
            return False
    except httpx.HTTPError as e:
        logger.error(f"ListAvailableProfiles failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Server response: {e.response.status_code} {e.response.text}")
        return False


def test_get_models():
    """Tests the ListAvailableModels endpoint."""
    logger.info("Testing /ListAvailableModels...")
    url = f"{KIRO_API_HOST}/ListAvailableModels"
    params = {
        "origin": "AI_EDITOR",
        "profileArn": PROFILE_ARN
    }

    try:
        response = httpx.get(url, headers=HEADERS, params=params)
        response.raise_for_status()

        logger.info(f"Response status: {response.status_code}")
        logger.debug(f"Response (JSON):\n{json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        logger.success("ListAvailableModels test COMPLETED SUCCESSFULLY")
        return True
    except httpx.HTTPError as e:
        logger.error(f"ListAvailableModels test failed: {e}")
        return False


def test_generate_content():
    """Tests the generateAssistantResponse endpoint."""
    logger.info("Testing /generateAssistantResponse...")
    url = f"{KIRO_API_HOST}/generateAssistantResponse"
    
    payload = {
        "conversationState": {
            "agentContinuationId": str(uuid.uuid4()),
            "agentTaskType": "vibe",
            "chatTriggerType": "MANUAL",
            "conversationId": str(uuid.uuid4()),
            "currentMessage": {
                "userInputMessage": {
                    "content": "Hello! Say something short.",
                    "modelId": "claude-haiku-4.5",
                    "origin": "AI_EDITOR",
                    "userInputMessageContext": {
                        "tools": []
                    }
                }
            },
            "history": []
        }
    }
    
    # Only add profileArn if it's set and not AWS SSO OIDC
    # AWS SSO OIDC (Builder ID) users don't need profileArn and it causes 403 if sent
    if PROFILE_ARN and AUTH_TYPE != AuthType.AWS_SSO_OIDC:
        payload["profileArn"] = PROFILE_ARN

    try:
        with httpx.stream("POST", url, headers=HEADERS, json=payload) as response:
            response.raise_for_status()
            logger.info(f"Response status: {response.status_code}")
            logger.info("Streaming response:")

            for chunk in response.iter_bytes(chunk_size=1024):
                if chunk:
                    # Try to decode and find JSON
                    chunk_str = chunk.decode('utf-8', errors='ignore')
                    logger.debug(f"Chunk: {chunk_str[:200]}...")

        logger.success("generateAssistantResponse test COMPLETED")
        return True
    except httpx.HTTPError as e:
        logger.error(f"generateAssistantResponse test failed: {e}")
        return False


if __name__ == "__main__":
    logger.info(f"Starting Kiro API tests...")
    logger.info(f"  Credentials source: {cred_source}")
    logger.info(f"  Auth type: {AUTH_TYPE.value}")
    logger.info(f"  API Region: {API_REGION}")
    logger.info(f"  SSO Region: {SSO_REGION or 'not set (using API region)'}")
    logger.info(f"  API Host: {KIRO_API_HOST}")

    # Check if we already have a valid token from the database
    if AUTH_TOKEN:
        HEADERS['Authorization'] = f"Bearer {AUTH_TOKEN}"
        logger.info("Using existing valid access token from database")
        token_ok = True
    else:
        token_ok = refresh_auth_token()

    if token_ok:
        # Get profile ARN dynamically for AWS SSO OIDC users
        if AUTH_TYPE == AuthType.AWS_SSO_OIDC:
            get_profile_arn()
        
        models_ok = test_get_models()
        generate_ok = test_generate_content()

        if models_ok and generate_ok:
            logger.success(f"All tests passed successfully!")
            logger.success(f"  Auth type: {AUTH_TYPE.value}")
            logger.success(f"  Credentials: {cred_source}")
        else:
            logger.warning(f"One or more tests failed.")
    else:
        logger.error("Failed to refresh token. Tests not started.")
        logger.error(f"  Auth type: {AUTH_TYPE.value}")
        sso_region = SSO_REGION or API_REGION
        oidc_url = AWS_SSO_OIDC_TOKEN_URL or f"https://oidc.{sso_region}.amazonaws.com/token"
        logger.error(f"  Token URL: {oidc_url if AUTH_TYPE == AuthType.AWS_SSO_OIDC else KIRO_DESKTOP_TOKEN_URL}")
