"""
Temporary storage for bootstrap tokens and generated content.

In production, this should be replaced with Redis or similar.
"""
import os
import time
import uuid
import shutil
import threading
from pathlib import Path
from typing import Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class BootstrapSession:
    """Represents a generated bootstrap session."""
    token: str
    created_at: datetime
    expires_at: datetime
    config: Dict[str, Any]
    content_path: Path
    accessed: bool = False
    one_time: bool = True
    
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at
    
    def is_valid(self) -> bool:
        """Check if session is valid for access."""
        if self.is_expired():
            return False
        if self.one_time and self.accessed:
            return False
        return True


class TokenStorage:
    """
    In-memory storage for bootstrap tokens.
    
    Features:
    - One-time use tokens (configurable)
    - Auto-expiration
    - Periodic cleanup of expired sessions
    """
    
    def __init__(
        self,
        storage_dir: str = "/tmp/k8s-bootstrap-sessions",
        default_ttl_minutes: int = 60,
        cleanup_interval_seconds: int = 300
    ):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.default_ttl = timedelta(minutes=default_ttl_minutes)
        self.sessions: Dict[str, BootstrapSession] = {}
        self._lock = threading.Lock()
        
        # Start cleanup thread
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_interval = cleanup_interval_seconds
        self._running = True
        self._cleanup_thread.start()
    
    def create_session(
        self,
        config: Dict[str, Any],
        content_path: Path,
        ttl_minutes: Optional[int] = None,
        one_time: bool = True
    ) -> BootstrapSession:
        """
        Create a new bootstrap session.
        
        Args:
            config: The bootstrap configuration
            content_path: Path to generated content directory
            ttl_minutes: Time to live in minutes (default: 60)
            one_time: If True, token can only be used once
            
        Returns:
            BootstrapSession with unique token
        """
        token = self._generate_token()
        now = datetime.utcnow()
        ttl = timedelta(minutes=ttl_minutes) if ttl_minutes else self.default_ttl
        
        # Copy content to storage directory
        session_dir = self.storage_dir / token
        shutil.copytree(content_path, session_dir)
        
        session = BootstrapSession(
            token=token,
            created_at=now,
            expires_at=now + ttl,
            config=config,
            content_path=session_dir,
            one_time=one_time
        )
        
        with self._lock:
            self.sessions[token] = session
        
        return session
    
    def get_session(self, token: str, mark_accessed: bool = True) -> Optional[BootstrapSession]:
        """
        Get a session by token.
        
        Args:
            token: The session token
            mark_accessed: If True, marks the session as accessed
            
        Returns:
            BootstrapSession if valid, None otherwise
        """
        with self._lock:
            session = self.sessions.get(token)
            
            if not session:
                return None
            
            if not session.is_valid():
                # Clean up expired/used session
                self._delete_session(token)
                return None
            
            if mark_accessed:
                session.accessed = True
            
            return session
    
    def peek_session(self, token: str) -> Optional[BootstrapSession]:
        """Get session without marking it as accessed."""
        return self.get_session(token, mark_accessed=False)
    
    def delete_session(self, token: str) -> bool:
        """Delete a session."""
        with self._lock:
            return self._delete_session(token)
    
    def _delete_session(self, token: str) -> bool:
        """Internal delete (assumes lock is held)."""
        session = self.sessions.pop(token, None)
        if session and session.content_path.exists():
            shutil.rmtree(session.content_path, ignore_errors=True)
        return session is not None
    
    def _generate_token(self) -> str:
        """Generate a unique token."""
        # Use UUID4 for randomness + timestamp for uniqueness
        return f"{uuid.uuid4().hex[:16]}{int(time.time())}"
    
    def _cleanup_loop(self):
        """Periodically clean up expired sessions."""
        while self._running:
            time.sleep(self._cleanup_interval)
            self._cleanup_expired()
    
    def _cleanup_expired(self):
        """Remove all expired sessions."""
        with self._lock:
            expired = [
                token for token, session in self.sessions.items()
                if session.is_expired()
            ]
            for token in expired:
                self._delete_session(token)
    
    def shutdown(self):
        """Stop the cleanup thread."""
        self._running = False


# Global storage instance
_storage: Optional[TokenStorage] = None


def get_storage() -> TokenStorage:
    """Get or create the global storage instance."""
    global _storage
    if _storage is None:
        storage_dir = os.environ.get(
            "K8S_BOOTSTRAP_STORAGE_DIR",
            "/tmp/k8s-bootstrap-sessions"
        )
        ttl = int(os.environ.get("K8S_BOOTSTRAP_TOKEN_TTL_MINUTES", "60"))
        _storage = TokenStorage(storage_dir=storage_dir, default_ttl_minutes=ttl)
    return _storage
