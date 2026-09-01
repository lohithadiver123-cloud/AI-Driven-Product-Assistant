"""Password hashing and verification service using Argon2id."""
import logging
from typing import Tuple
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHash

logger = logging.getLogger("ai_product_assistant.password")

# Configure Argon2id hasher with recommended security parameters
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MiB
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_password(plain_password: str) -> str:
    """
    Hash a plain-text password using Argon2id.
    
    Args:
        plain_password: The user's plain-text password.
        
    Returns:
        The Argon2id password hash string.
    """
    if not plain_password:
        raise ValueError("Password cannot be empty.")
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain-text password against an Argon2id hash.
    
    Args:
        plain_password: The plain-text password to check.
        hashed_password: The stored Argon2id hash.
        
    Returns:
        True if the password matches, False otherwise.
    """
    if not plain_password or not hashed_password:
        return False
    try:
        return _hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHash):
        return False
    except Exception as exc:
        logger.error("Unexpected error during password verification: %s", exc)
        return False


def validate_password_strength(password: str) -> Tuple[bool, str]:
    """
    Validate that a password meets security baseline requirements.
    
    Requirements:
      - At least 8 characters
      - Contains at least one letter
      - Contains at least one number
    """
    if not password or len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not any(c.isalpha() for c in password):
        return False, "Password must contain at least one letter."
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number."
    return True, ""
