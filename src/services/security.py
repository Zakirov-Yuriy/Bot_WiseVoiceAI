"""
Security utilities for file validation, API key management, and audit logging.
"""
import logging
import hashlib
import mimetypes
import os
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import asyncio
import time
from datetime import datetime

from ..config import settings
from ..exceptions import FileProcessingError, APIError
from ..database import async_session
from ..models import AuditLog

logger = logging.getLogger(__name__)

# File validation constants - dynamically loaded from settings
ALLOWED_MIME_TYPES = {
    # Audio formats
    'audio/mpeg', 'audio/mp3', 'audio/m4a', 'audio/x-m4a',
    'audio/flac', 'audio/wav', 'audio/x-wav', 'audio/ogg',
    'audio/opus', 'audio/webm',
    # Video formats
    'video/mp4', 'video/x-msvideo', 'video/quicktime',
    'video/x-matroska', 'video/webm', 'video/x-flv'
}

# Malicious file signatures (file headers)
MALICIOUS_SIGNATURES = [
    b'\x4D\x5A',  # MZ (Windows executable)
    b'\x7F\x45\x4C\x46',  # ELF (Linux executable)
    b'\x23\x21',  # Shebang (script files)
    b'\x50\x4B\x03\x04',  # ZIP/PKZIP
    b'\x52\x61\x72\x21',  # RAR
    b'\x1F\x8B',  # GZIP
]

class SecurityService:
    """Service for handling security-related operations."""

    @staticmethod
    def validate_file_size(file_path: str) -> bool:
        """Validate file size against maximum allowed size from config."""
        try:
            max_size = settings.max_file_size_mb * 1024 * 1024  # Convert MB to bytes
            file_size = os.path.getsize(file_path)
            if file_size > max_size:
                logger.warning(f"File size {file_size} exceeds maximum {max_size}")
                return False
            return True
        except OSError as e:
            logger.error(f"Error checking file size: {e}")
            return False

    @staticmethod
    def validate_mime_type(file_path: str) -> Tuple[bool, str]:
        """Validate file MIME type against allowed types."""
        try:
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type is None:
                # Fallback: try to guess from file extension
                _, ext = os.path.splitext(file_path)
                mime_type = mimetypes.types_map.get(ext.lower(), 'application/octet-stream')

            if mime_type not in ALLOWED_MIME_TYPES:
                logger.warning(f"Disallowed MIME type: {mime_type}")
                return False, mime_type
            return True, mime_type
        except Exception as e:
            logger.error(f"Error detecting MIME type: {e}")
            return False, "unknown"

    @staticmethod
    def check_malicious_content(file_path: str) -> bool:
        """Check file for malicious content by examining file headers."""
        try:
            with open(file_path, 'rb') as f:
                header = f.read(4)  # Read first 4 bytes

            for signature in MALICIOUS_SIGNATURES:
                if header.startswith(signature):
                    logger.warning(f"Detected potentially malicious file signature: {signature.hex()}")
                    return True
            return False
        except Exception as e:
            logger.error(f"Error checking file content: {e}")
            return True  # Err on the side of caution

    @staticmethod
    def calculate_file_hash(file_path: str) -> str:
        """Calculate SHA256 hash of file for integrity checking."""
        try:
            sha256 = hashlib.sha256()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except Exception as e:
            logger.error(f"Error calculating file hash: {e}")
            return ""

    @classmethod
    def validate_file_security(cls, file_path: str) -> Tuple[bool, str]:
        """
        Comprehensive file security validation.

        Returns:
            Tuple[bool, str]: (is_valid, error_message)
        """
        # Check file size
        if not cls.validate_file_size(file_path):
            return False, "File size exceeds maximum allowed limit"

        # Check MIME type
        is_valid_mime, mime_type = cls.validate_mime_type(file_path)
        if not is_valid_mime:
            return False, f"Unsupported file type: {mime_type}"

        # Check for malicious content
        if cls.check_malicious_content(file_path):
            return False, "File contains potentially malicious content"

        return True, ""

class APIKeyManager:
    """Manager for API key rotation and secure storage."""

    def __init__(self):
        self._keys = settings.openrouter_api_key_list.copy()
        self._current_key_index = 0
        self._key_usage_count = {}
        self._key_last_used = {}
        self._max_usage_per_key = settings.api_key_max_usage
        self._key_rotation_interval = settings.api_key_rotation_interval_hours * 3600  # Convert hours to seconds

    def get_current_key(self) -> Optional[str]:
        """Get current API key with rotation logic."""
        if not self._keys:
            return None

        current_time = time.time()
        current_key = self._keys[self._current_key_index]

        # Check if key needs rotation
        usage_count = self._key_usage_count.get(current_key, 0)
        last_used = self._key_last_used.get(current_key, 0)

        if (usage_count >= self._max_usage_per_key or
            current_time - last_used > self._key_rotation_interval):
            self._rotate_key()

        return self._keys[self._current_key_index]

    def mark_key_used(self, key: str):
        """Mark API key as used for rotation tracking."""
        self._key_usage_count[key] = self._key_usage_count.get(key, 0) + 1
        self._key_last_used[key] = time.time()

    def _rotate_key(self):
        """Rotate to next available key."""
        if len(self._keys) > 1:
            self._current_key_index = (self._current_key_index + 1) % len(self._keys)
            logger.info(f"Rotated to API key index: {self._current_key_index}")

    def get_key_health_status(self) -> Dict[str, Any]:
        """Get health status of all API keys."""
        status = {}
        current_time = time.time()

        for i, key in enumerate(self._keys):
            masked_key = key[:8] + "..." if len(key) > 8 else key
            status[f"key_{i}"] = {
                "masked": masked_key,
                "usage_count": self._key_usage_count.get(key, 0),
                "last_used": self._key_last_used.get(key, 0),
                "is_current": i == self._current_key_index,
                "needs_rotation": (
                    self._key_usage_count.get(key, 0) >= self._max_usage_per_key or
                    current_time - self._key_last_used.get(key, 0) > self._key_rotation_interval
                )
            }

        return status

class AuditLogger:
    """Service for logging security and business events."""

    @staticmethod
    async def log_payment_event(
        user_id: int,
        event_type: str,
        amount: Optional[float] = None,
        payment_id: Optional[str] = None,
        status: str = "success",
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log payment-related events."""
        await AuditLogger._log_event(
            user_id=user_id,
            event_type=f"payment_{event_type}",
            details={
                "amount": amount,
                "payment_id": payment_id,
                "status": status,
                **(metadata or {})
            }
        )

    @staticmethod
    async def log_referral_event(
        user_id: int,
        event_type: str,
        referrer_id: Optional[int] = None,
        referral_code: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log referral-related events."""
        await AuditLogger._log_event(
            user_id=user_id,
            event_type=f"referral_{event_type}",
            details={
                "referrer_id": referrer_id,
                "referral_code": referral_code,
                **(metadata or {})
            }
        )

    @staticmethod
    async def log_file_processing_event(
        user_id: int,
        file_hash: str,
        file_size: int,
        mime_type: str,
        status: str,
        processing_time: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log file processing events."""
        await AuditLogger._log_event(
            user_id=user_id,
            event_type="file_processing",
            details={
                "file_hash": file_hash,
                "file_size": file_size,
                "mime_type": mime_type,
                "status": status,
                "processing_time": processing_time,
                **(metadata or {})
            }
        )

    @staticmethod
    async def log_security_event(
        user_id: int,
        event_type: str,
        severity: str = "info",
        details: Optional[Dict[str, Any]] = None
    ):
        """Log security-related events."""
        await AuditLogger._log_event(
            user_id=user_id,
            event_type=f"security_{event_type}",
            details={
                "severity": severity,
                **(details or {})
            }
        )

    @staticmethod
    async def _log_event(
        user_id: int,
        event_type: str,
        details: Dict[str, Any]
    ):
        """Internal method to log events to database."""
        try:
            async with async_session() as session:
                audit_log = AuditLog(
                    user_id=user_id,
                    event_type=event_type,
                    details=details,
                    timestamp=datetime.utcnow(),
                    ip_address=details.get("ip_address"),
                    user_agent=details.get("user_agent")
                )
                session.add(audit_log)
                await session.commit()

                logger.info(f"Audit log: {event_type} for user {user_id}")

        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")

# Global instances
security_service = SecurityService()
api_key_manager = APIKeyManager()
audit_logger = AuditLogger()
