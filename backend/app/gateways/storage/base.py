from pathlib import Path
from typing import Protocol


class Storage(Protocol):
    def put_file(self, key: str, path: Path) -> None: ...

    def delete(self, key: str) -> None: ...

    def download_to_path(self, key: str, path: Path) -> None: ...

    def copy_file(self, source_key: str, target_key: str) -> None:
        """Copy an object to a new key.

        Used when the same file is printed again: the second order owns
        its own object, so each one has its own retention window and
        deleting one never breaks the other.
        """
        ...

    def presigned_get_url(
        self,
        key: str,
        *,
        expires_seconds: int = 300,
        download_filename: str | None = None,
    ) -> str: ...

    def health(self) -> bool: ...
