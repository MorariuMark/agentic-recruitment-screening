"""Persist a local signing secret without rotating it on reload or worker startup."""
import os
from pathlib import Path
import secrets
import tempfile


def load_or_create_session_secret(filename: str) -> str:
    path = Path(filename).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        temporary = None
        try:
            # Publish a complete file atomically. Only one concurrent worker wins;
            # every worker then reads that same key. Never overwrite an existing key.
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             prefix=".auth-secret-", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(secrets.token_urlsafe(48))
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                pass
        except OSError as error:
            raise RuntimeError("Cannot persist the session signing key. Set AUTH_SECRET_KEY or a writable AUTH_SECRET_FILE.") from error
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    secret = path.read_text(encoding="utf-8").strip()
    if len(secret) < 32:
        raise ValueError("Stored session signing key is invalid. Restore AUTH_SECRET_FILE or configure AUTH_SECRET_KEY.")
    return secret
