import hashlib
import time
from typing import Optional, Dict

from loguru import logger

from kiro.auth import KiroAuthManager


class MultiUserManager:
    """
    Manages per-user KiroAuthManager instances keyed by refresh token hash.
    
    First request with X-Kiro-* headers creates and caches an auth manager.
    Subsequent requests with the same refresh token reuse the cached instance.
    """

    def __init__(self, max_users: int = 50, ttl_seconds: int = 7 * 24 * 3600):
        self._cache: Dict[str, dict] = {}
        self._max_users = max_users
        self._ttl_seconds = ttl_seconds

    def _hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def _evict_stale(self) -> None:
        now = time.time()
        stale = [k for k, v in self._cache.items() if now - v["last_used"] > self._ttl_seconds]
        for k in stale:
            del self._cache[k]
            logger.info(f"[multi-user] Evicted stale user ({k[:8]}...)")

    def _evict_lru(self) -> None:
        if len(self._cache) >= self._max_users:
            oldest_key = min(self._cache, key=lambda k: self._cache[k]["last_used"])
            del self._cache[oldest_key]
            logger.info(f"[multi-user] Evicted LRU user ({oldest_key[:8]}...)")

    def get_or_create(
        self,
        refresh_token: str,
        access_token: Optional[str] = None,
        auth_method: Optional[str] = None,
        profile_arn: Optional[str] = None,
        region: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        client_id_hash: Optional[str] = None,
    ) -> KiroAuthManager:
        key_hash = self._hash_token(refresh_token)

        if key_hash in self._cache:
            self._cache[key_hash]["last_used"] = time.time()
            return self._cache[key_hash]["auth_manager"]

        self._evict_stale()
        self._evict_lru()

        resolved_client_id = client_id
        resolved_client_secret = client_secret

        if not resolved_client_id and client_id_hash:
            import json
            from pathlib import Path
            reg_path = Path.home() / ".aws" / "sso" / "cache" / f"{client_id_hash}.json"
            if reg_path.exists():
                try:
                    reg_data = json.loads(reg_path.read_text())
                    resolved_client_id = reg_data.get("clientId")
                    resolved_client_secret = reg_data.get("clientSecret")
                except Exception:
                    pass

        auth_manager = KiroAuthManager(
            refresh_token=refresh_token,
            profile_arn=profile_arn,
            region=region or "us-east-1",
            client_id=resolved_client_id,
            client_secret=resolved_client_secret,
        )

        if access_token:
            auth_manager._access_token = access_token
        
        if region:
            auth_manager._sso_region = region

        self._cache[key_hash] = {
            "auth_manager": auth_manager,
            "last_used": time.time(),
        }

        logger.info(f"[multi-user] Registered new user ({key_hash[:8]}...)")
        return auth_manager

    @property
    def user_count(self) -> int:
        return len(self._cache)


multi_user_manager = MultiUserManager()
