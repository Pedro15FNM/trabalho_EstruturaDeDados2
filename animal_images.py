"""Lookup e cache local de imagens de táxons do iNaturalist.

A rede é acessada somente quando o jogo solicita explicitamente um táxon. O
módulo não importa Pygame e pode ser testado isoladamente com urllib mockado.
"""

from __future__ import annotations

import json
import re
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_CACHE_DIR = DATA_DIR / "animal_images"
API_URL = "https://api.inaturalist.org/v1/taxa/{taxon_id}"
TAXON_URL = "https://www.inaturalist.org/taxa/{taxon_id}"
REQUEST_TIMEOUT = 8.0
MAX_IMAGE_BYTES = 12 * 1024 * 1024
USER_AGENT = "SkylineSkipList/1.0 (animal image cache)"


@dataclass(frozen=True, slots=True)
class AnimalImage:
    taxon_id: str | None
    taxon_url: str | None
    image_path: Path | None = None
    image_url: str | None = None
    attribution: str | None = None
    license_code: str | None = None

    @property
    def available(self) -> bool:
        return self.image_path is not None


def extract_inaturalist_id(value: str | int | None) -> str | None:
    """Extrai um ID positivo de URL oficial de táxon ou de valor numérico."""
    if value is None or isinstance(value, bool):
        return None
    raw = str(value).strip()
    if raw.isdigit():
        return raw if int(raw) > 0 else None
    try:
        parsed = urlparse(raw)
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or parsed.hostname not in {
        "inaturalist.org",
        "www.inaturalist.org",
    }:
        return None
    match = re.fullmatch(r"/taxa/(\d+)/?", parsed.path)
    if not match or int(match.group(1)) <= 0:
        return None
    return match.group(1)


def inaturalist_taxon_url(taxon_id: str | int | None) -> str | None:
    parsed_id = extract_inaturalist_id(taxon_id)
    return TAXON_URL.format(taxon_id=parsed_id) if parsed_id else None


class AnimalImageService:
    """Busca a foto padrão, mantém cache no disco e oferece chamadas em background."""

    def __init__(
        self,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        *,
        timeout: float = REQUEST_TIMEOUT,
        max_workers: int = 1,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.timeout = timeout
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="inat-image"
        )
        self._lock = threading.Lock()
        self._futures: dict[str, Future[AnimalImage]] = {}

    def request(self, taxon_id: str | int | None) -> Future[AnimalImage]:
        parsed_id = extract_inaturalist_id(taxon_id)
        if parsed_id is None:
            future: Future[AnimalImage] = Future()
            future.set_result(AnimalImage(None, None))
            return future
        with self._lock:
            future = self._futures.get(parsed_id)
            if future is None:
                if len(self._futures) >= 128:
                    for old_id, old_future in list(self._futures.items()):
                        if old_future.done():
                            self._futures.pop(old_id, None)
                        if len(self._futures) < 64:
                            break
                future = self._executor.submit(self.get_image, parsed_id)
                self._futures[parsed_id] = future
            return future

    def get_image(self, taxon_id: str | int | None) -> AnimalImage:
        parsed_id = extract_inaturalist_id(taxon_id)
        if parsed_id is None:
            return AnimalImage(None, None)
        taxon_url = inaturalist_taxon_url(parsed_id)
        image_path = self.cache_dir / f"{parsed_id}.jpg"
        metadata_path = self.cache_dir / f"{parsed_id}.json"

        cached = self._read_cache(parsed_id, taxon_url, image_path, metadata_path)
        if cached is not None:
            return cached

        try:
            response = self._read_url(API_URL.format(taxon_id=parsed_id))
            payload = json.loads(response.decode("utf-8"))
            taxon = self._first_taxon(payload)
        except (HTTPError, URLError, TimeoutError, OSError, UnicodeError, ValueError):
            return AnimalImage(parsed_id, taxon_url)
        except Exception:
            return AnimalImage(parsed_id, taxon_url)

        photo = taxon.get("default_photo") if isinstance(taxon, dict) else None
        if not isinstance(photo, dict):
            result = AnimalImage(parsed_id, taxon_url)
            self._write_metadata(metadata_path, result, available=False)
            return result

        urls = list(dict.fromkeys(
            url for url in (
                photo.get("medium_url"),
                photo.get("square_url"),
                photo.get("url"),
            ) if isinstance(url, str) and url.startswith(("https://", "http://"))
        ))
        attribution = self._optional_text(photo.get("attribution"))
        license_code = self._optional_text(photo.get("license_code"))
        for image_url in urls:
            try:
                image_data = self._read_url(image_url, max_bytes=MAX_IMAGE_BYTES)
                if not self._looks_like_image(image_data):
                    continue
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                temporary_path = image_path.with_suffix(".jpg.tmp")
                temporary_path.write_bytes(image_data)
                temporary_path.replace(image_path)
                result = AnimalImage(
                    parsed_id, taxon_url, image_path, image_url, attribution, license_code
                )
                self._write_metadata(metadata_path, result, available=True)
                return result
            except (HTTPError, URLError, TimeoutError, OSError, ValueError):
                continue
            except Exception:
                continue

        result = AnimalImage(parsed_id, taxon_url, None, None, attribution, license_code)
        self._write_metadata(metadata_path, result, available=False)
        return result

    def _read_cache(
        self,
        taxon_id: str,
        taxon_url: str,
        image_path: Path,
        metadata_path: Path,
    ) -> AnimalImage | None:
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        if not isinstance(metadata, dict) or metadata.get("taxon_id") != taxon_id:
            return None
        attribution = self._optional_text(metadata.get("attribution"))
        license_code = self._optional_text(metadata.get("license_code"))
        image_url = self._optional_text(metadata.get("image_url"))
        if metadata.get("image_available") is False:
            return AnimalImage(taxon_id, taxon_url, None, image_url, attribution, license_code)
        if image_path.is_file() and image_path.stat().st_size > 0:
            return AnimalImage(
                taxon_id, taxon_url, image_path, image_url, attribution, license_code
            )
        return None

    def _write_metadata(
        self, path: Path, image: AnimalImage, *, available: bool
    ) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            data = {
                "taxon_id": image.taxon_id,
                "taxon_url": image.taxon_url,
                "image_url": image.image_url,
                "attribution": image.attribution,
                "license_code": image.license_code,
                "image_available": available,
            }
            temporary_path = path.with_suffix(".json.tmp")
            temporary_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temporary_path.replace(path)
        except OSError:
            pass

    def _read_url(self, url: str, *, max_bytes: int = 2 * 1024 * 1024) -> bytes:
        request = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=self.timeout) as response:
            status = getattr(response, "status", getattr(response, "code", 200))
            if status < 200 or status >= 300:
                raise URLError(f"HTTP status {status}")
            payload = response.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise ValueError("Response exceeds configured size limit")
        return payload

    @staticmethod
    def _first_taxon(payload: Any) -> dict[str, Any]:
        if isinstance(payload, list):
            return payload[0] if payload and isinstance(payload[0], dict) else {}
        if isinstance(payload, dict):
            results = payload.get("results")
            if isinstance(results, list):
                return results[0] if results and isinstance(results[0], dict) else {}
            return payload
        return {}

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    @staticmethod
    def _looks_like_image(payload: bytes) -> bool:
        return payload.startswith((
            b"\xff\xd8\xff",
            b"\x89PNG\r\n\x1a\n",
            b"GIF87a",
            b"GIF89a",
            b"RIFF",
            b"BM",
        ))

    def shutdown(self, *, wait: bool = False) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=True)
