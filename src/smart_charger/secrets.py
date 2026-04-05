from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

SECRETS_PATH = Path.home() / ".config" / "smart-charger" / "secrets.toml"


class Secrets:
    def __init__(self, secrets_path: Path | None = None):
        self._secrets_path = secrets_path or SECRETS_PATH
        self._cache: dict | None = None

    def _load(self) -> dict:
        if self._cache is not None:
            return self._cache

        if not self._secrets_path.exists():
            raise FileNotFoundError(f"Secrets file not found at {self._secrets_path}")

        try:
            if sys.version_info >= (3, 11):
                import tomllib

                with self._secrets_path.open("rb") as f:
                    self._cache = tomllib.load(f)
                logger.info(f"Loaded secrets from {self._secrets_path}")
                return self._cache
            else:
                import tomli

                with self._secrets_path.open("rb") as f:
                    self._cache = tomli.load(f)
                logger.info(f"Loaded secrets from {self._secrets_path}")
                return self._cache
        except Exception as e:
            logger.error(f"Failed to load secrets from {self._secrets_path}: {e}")
            raise

    def _get_nested(self, section: str, key: str) -> str | None:
        secrets = self._load()
        return secrets.get(section, {}).get(key)

    def get(self, key: str, default: str | None = None) -> str | None:
        try:
            secrets = self._load()
            if isinstance(key, tuple):
                section, subkey = key
                return secrets.get(section, {}).get(subkey, default)
            return secrets.get(key, default)
        except FileNotFoundError:
            if default is not None:
                return default
            raise

    @property
    def installation_id(self) -> str:
        return self._get_nested("zaptec", "installation_id") or ""

    @property
    def charger_id(self) -> str:
        return self._get_nested("zaptec", "charger_id") or ""

    @property
    def username(self) -> str:
        return self._get_nested("zaptec", "username") or ""

    @property
    def password(self) -> str:
        return self._get_nested("zaptec", "password") or ""

    @property
    def tibber_api_key(self) -> str:
        return self._get_nested("tibber", "api_key") or ""

    @property
    def zaptec_refresh_token(self) -> str:
        return self._get_nested("zaptec", "refresh_token") or ""

    @property
    def zaptec_access_token(self) -> str:
        return self._get_nested("zaptec", "access_token") or ""

    @property
    def zaptec_token_expires_at(self) -> str:
        return self._get_nested("zaptec", "token_expires_at") or ""

    def save_zaptec_token(self, access_token: str, expires_in: int) -> None:
        import datetime

        logger.info(
            "save_zaptec_token called with token: %s",
            access_token[:50] if access_token else "None",
        )
        content = self._secrets_path.read_text()
        lines = content.splitlines()
        new_lines = []
        in_zaptec = False
        in_zaptec_section = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("[zaptec]"):
                in_zaptec = True
                in_zaptec_section = True
            elif stripped.startswith("[") and in_zaptec:
                in_zaptec = False
                in_zaptec_section = False

            if in_zaptec_section:
                if "access_token" in line:
                    new_lines.append(f'access_token = "{access_token}"')
                    continue
                elif "token_expires_at" in line:
                    expires_at = datetime.datetime.now() + datetime.timedelta(
                        seconds=expires_in - 60
                    )
                    new_lines.append(f'token_expires_at = "{expires_at.isoformat()}"')
                    continue

            new_lines.append(line)

        self._secrets_path.write_text("\n".join(new_lines) + "\n")
        self._cache = None
        logger.info(f"Saved zaptec access token to {self._secrets_path}")

    @property
    def ctek_client_id(self) -> str:
        return self._get_nested("ctek", "client_id") or ""

    @property
    def ctek_client_secret(self) -> str:
        return self._get_nested("ctek", "client_secret") or ""

    @property
    def ctek_username(self) -> str:
        return self._get_nested("ctek", "username") or ""

    @property
    def ctek_password(self) -> str:
        return self._get_nested("ctek", "password") or ""

    @property
    def ctek_device_id(self) -> str:
        return self._get_nested("ctek", "device_id") or ""

    @property
    def ctek_access_token(self) -> str:
        return self._get_nested("ctek", "access_token") or ""

    @property
    def ctek_refresh_token(self) -> str:
        return self._get_nested("ctek", "refresh_token") or ""

    @property
    def ctek_token_expires_at(self) -> str:
        return self._get_nested("ctek", "token_expires_at") or ""

    def save_ctek_token(
        self, access_token: str, refresh_token: str | None, expires_in: int
    ) -> None:
        import datetime

        logger.info(
            "save_ctek_token called with token: %s",
            access_token[:50] if access_token else "None",
        )
        content = self._secrets_path.read_text()
        lines = content.splitlines()
        new_lines = []
        in_ctek_section = False
        updated_access = False
        updated_refresh = False
        updated_expires = False

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("[ctek]"):
                in_ctek_section = True
            elif stripped.startswith("["):
                in_ctek_section = False

            if in_ctek_section:
                if "access_token" in line and "=" in line:
                    new_lines.append(f'access_token = "{access_token}"')
                    updated_access = True
                    continue
                elif "refresh_token" in line and "=" in line:
                    new_lines.append(f'refresh_token = "{refresh_token or ""}"')
                    updated_refresh = True
                    continue
                elif "token_expires_at" in line and "=" in line:
                    expires_at = datetime.datetime.now() + datetime.timedelta(
                        seconds=expires_in - 60
                    )
                    new_lines.append(f'token_expires_at = "{expires_at.isoformat()}"')
                    updated_expires = True
                    continue

            new_lines.append(line)

        if not updated_access:
            new_lines.append("")
            new_lines.append("[ctek]")
            new_lines.append(f'access_token = "{access_token}"')
        if not updated_refresh and refresh_token:
            if not any(line.strip() == "[ctek]" for line in new_lines):
                new_lines.append("")
                new_lines.append("[ctek]")
            new_lines.append(f'refresh_token = "{refresh_token}"')
        if not updated_expires:
            if not any(line.strip() == "[ctek]" for line in new_lines):
                new_lines.append("")
                new_lines.append("[ctek]")
            expires_at = datetime.datetime.now() + datetime.timedelta(
                seconds=expires_in - 60
            )
            new_lines.append(f'token_expires_at = "{expires_at.isoformat()}"')

        self._secrets_path.write_text("\n".join(new_lines) + "\n")
        self._cache = None
        logger.info(f"Saved ctek access token to {self._secrets_path}")
