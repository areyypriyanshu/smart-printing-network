import time
from pathlib import Path
from urllib.parse import quote


class MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_file(self, key: str, path: Path) -> None:
        self.objects[key] = path.read_bytes()

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def presigned_get_url(
        self,
        key: str,
        *,
        expires_seconds: int = 300,
        download_filename: str | None = None,
    ) -> str:
        params = {"expires": str(int(time.time()) + expires_seconds)}
        if download_filename is not None:
            params["download"] = download_filename
        query = "&".join(f"{name}={quote(value)}" for name, value in params.items())
        return f"memory://{key}?{query}"

    def health(self) -> bool:
        return True
