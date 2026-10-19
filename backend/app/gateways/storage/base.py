from pathlib import Path
from typing import Protocol


class Storage(Protocol):
    def put_file(self, key: str, path: Path) -> None: ...

    def delete(self, key: str) -> None: ...

    def presigned_get_url(
        self,
        key: str,
        *,
        expires_seconds: int = 300,
        download_filename: str | None = None,
    ) -> str: ...

    def health(self) -> bool: ...
