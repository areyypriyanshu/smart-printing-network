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

    def download_to_path(self, key: str, path: Path) -> None:
        path.write_bytes(self.objects[key])

    def copy_file(self, source_key: str, target_key: str) -> None:
        if source_key not in self.objects:
            raise KeyError(source_key)
        self.objects[target_key] = self.objects[source_key]

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
