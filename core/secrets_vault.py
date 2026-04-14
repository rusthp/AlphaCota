"""
core/secrets_vault.py — AES-256-GCM encrypted secrets vault.

Encryption scheme:
  KDF   : PBKDF2-HMAC-SHA256, 600_000 iterations, 32-byte key
  Salt  : 16 bytes random, stored as first 16 bytes of vault file
  Cipher: AES-256-GCM, 12-byte nonce prepended to each ciphertext
  Format: vault is a JSON object mapping secret name → hex(nonce + ciphertext + tag)

Vault file: data/.vault  (gitignored)

Usage:
    from core.secrets_vault import init_vault, store_secret, load_secret

    init_vault("my-master-password")
    store_secret("POLYMARKET_PRIVATE_KEY", "0xdeadbeef...")
    key = load_secret("POLYMARKET_PRIVATE_KEY")

CLI (encrypt a secret interactively):
    python -m core.secrets_vault
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VAULT_PATH = Path("data/.vault")
_KDF_ITERATIONS = 600_000
_SALT_LEN = 16
_NONCE_LEN = 12
_KEY_LEN = 32  # AES-256


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 32-byte AES key from password + salt using PBKDF2-HMAC-SHA256."""
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _KDF_ITERATIONS,
        dklen=_KEY_LEN,
    )


def _load_vault_raw() -> tuple[bytes, dict[str, str]]:
    """Read vault file and return (salt, secrets_dict). Raises FileNotFoundError if absent."""
    if not _VAULT_PATH.exists():
        raise FileNotFoundError(f"Vault not found at {_VAULT_PATH}. Run init_vault() first.")
    raw = _VAULT_PATH.read_bytes()
    salt = raw[:_SALT_LEN]
    payload = json.loads(raw[_SALT_LEN:].decode("utf-8"))
    return salt, payload


def _write_vault_raw(salt: bytes, payload: dict[str, str]) -> None:
    """Write salt + JSON payload to vault file with restrictive permissions."""
    _VAULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = salt + json.dumps(payload).encode("utf-8")
    _VAULT_PATH.write_bytes(data)
    # Restrict to owner read/write only (Unix); no-op on Windows
    try:  # noqa: SIM105 — contextlib.suppress not available in all Python 3.11 builds on Windows
        os.chmod(_VAULT_PATH, 0o600)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def init_vault(password: str) -> None:
    """
    Create a new vault with a fresh random salt.
    Safe to call on an existing vault — if vault already exists, this is a no-op
    (to avoid accidentally destroying secrets). To re-key, delete data/.vault manually.
    """
    if _VAULT_PATH.exists():
        return
    salt = secrets.token_bytes(_SALT_LEN)
    _write_vault_raw(salt, {})


def store_secret(name: str, value: str, password: str) -> None:
    """
    Encrypt `value` with AES-256-GCM and store it under `name` in the vault.

    Args:
        name: Secret identifier (e.g. "POLYMARKET_PRIVATE_KEY").
        value: Plaintext secret value.
        password: Master vault password used to derive the AES key.
    """
    salt, payload = _load_vault_raw()
    key = _derive_key(password, salt)
    aesgcm = AESGCM(key)
    nonce = secrets.token_bytes(_NONCE_LEN)
    ciphertext = aesgcm.encrypt(nonce, value.encode("utf-8"), name.encode("utf-8"))
    # Store as hex: nonce || ciphertext+tag
    payload[name] = (nonce + ciphertext).hex()
    _write_vault_raw(salt, payload)


def load_secret(name: str, password: str) -> str:
    """
    Decrypt and return the secret stored under `name`.

    Args:
        name: Secret identifier.
        password: Master vault password.

    Returns:
        Decrypted plaintext value.

    Raises:
        KeyError: Secret not found in vault.
        ValueError: Wrong password or tampered ciphertext.
        FileNotFoundError: Vault does not exist.
    """
    salt, payload = _load_vault_raw()
    if name not in payload:
        raise KeyError(f"Secret '{name}' not found in vault.")
    raw = bytes.fromhex(payload[name])
    nonce = raw[:_NONCE_LEN]
    ciphertext = raw[_NONCE_LEN:]
    key = _derive_key(password, salt)
    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, name.encode("utf-8"))
    except Exception as exc:
        raise ValueError("Decryption failed — wrong password or corrupted vault.") from exc
    return plaintext.decode("utf-8")


def load_secret_with_env_fallback(
    name: str,
    password: str | None,
    env_var: str | None = None,
) -> str:
    """
    Load a secret from vault if available; fall back to environment variable.

    Used in paper mode where no vault password is configured:
        load_secret_with_env_fallback("POLYMARKET_PRIVATE_KEY", None, "POLYMARKET_PRIVATE_KEY")

    Args:
        name: Vault secret name.
        password: Vault master password. If None, skips vault and uses env fallback.
        env_var: Environment variable name to fall back to. Defaults to `name`.

    Returns:
        Secret value.

    Raises:
        RuntimeError: Neither vault nor env var has the secret.
    """
    env_key = env_var or name

    if password and _VAULT_PATH.exists():
        try:
            return load_secret(name, password)
        except (KeyError, FileNotFoundError):
            pass  # fall through to env

    value = os.environ.get(env_key, "")
    if value:
        return value

    raise RuntimeError(
        f"Secret '{name}' not found in vault or environment variable '{env_key}'."
    )


def secret_exists(name: str) -> bool:
    """Return True if `name` is stored in the vault (does not decrypt)."""
    try:
        _, payload = _load_vault_raw()
        return name in payload
    except FileNotFoundError:
        return False


def list_secrets() -> list[str]:
    """Return the names of all secrets stored in the vault (no values)."""
    try:
        _, payload = _load_vault_raw()
        return list(payload.keys())
    except FileNotFoundError:
        return []


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import getpass
    import sys

    print("AlphaCota Secrets Vault")
    print("=" * 40)

    if not _VAULT_PATH.exists():
        print("No vault found. Creating new vault.")
        pw = getpass.getpass("Set master password: ")
        pw2 = getpass.getpass("Confirm master password: ")
        if pw != pw2:
            print("Passwords do not match.")
            sys.exit(1)
        init_vault(pw)
        print(f"Vault created at {_VAULT_PATH}")
    else:
        pw = getpass.getpass("Master password: ")

    print("\nCommands: store <name>, load <name>, list, quit")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line or line == "quit":
            break
        parts = line.split(None, 1)
        cmd = parts[0]
        if cmd == "list":
            names = list_secrets()
            print("Stored secrets:", names if names else "(none)")
        elif cmd == "store" and len(parts) == 2:
            val = getpass.getpass(f"Value for '{parts[1]}': ")
            store_secret(parts[1], val, pw)
            print(f"Stored '{parts[1]}'.")
        elif cmd == "load" and len(parts) == 2:
            try:
                val = load_secret(parts[1], pw)
                print(f"{parts[1]} = {val}")
            except (KeyError, ValueError) as e:
                print(f"Error: {e}")
        else:
            print("Unknown command.")
