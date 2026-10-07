from __future__ import annotations

import json
import pickle
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

import animal
from animal import AnimalRecord
from animal_images import (
    AnimalImageService,
    extract_inaturalist_id,
    inaturalist_taxon_url,
)
import database as db


class FakeResponse:
    def __init__(self, data: bytes, status: int = 200) -> None:
        self.data = data
        self.status = status

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, limit: int = -1) -> bytes:
        return self.data[:limit]


def _taxon_response(photo: dict[str, str] | None) -> bytes:
    return json.dumps([{"default_photo": photo}]).encode("utf-8")


class InatIdTests(unittest.TestCase):
    def test_extracts_numeric_id_from_official_taxon_url(self) -> None:
        self.assertEqual(
            extract_inaturalist_id("https://www.inaturalist.org/taxa/12345"),
            "12345",
        )
        self.assertEqual(extract_inaturalist_id("12345"), "12345")
        self.assertEqual(
            inaturalist_taxon_url("https://inaturalist.org/taxa/12345/"),
            "https://www.inaturalist.org/taxa/12345",
        )

    def test_rejects_invalid_urls_and_nonpositive_ids(self) -> None:
        for value in ("", "https://example.org/taxa/123", "https://www.inaturalist.org/observations/123", "0", -1):
            self.assertIsNone(extract_inaturalist_id(value))

    def test_missing_taxon_id_does_not_use_internal_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "taxa.csv"
            path.write_text(
                "id,scientificName,class,kingdom\n"
                "77,Animalia,Mammalia,Animalia\n",
                encoding="utf-8",
            )
            result = db._load_taxa_for_ids(path, {77})[77]
        self.assertEqual(result["inaturalist_id"], "")
        self.assertEqual(result["inaturalist_url"], "")

    def test_uses_identifier_when_taxon_id_column_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "taxa.csv"
            path.write_text(
                "id,identifier,scientificName,class,kingdom\n"
                "77,https://www.inaturalist.org/taxa/987,Animalia,Mammalia,Animalia\n",
                encoding="utf-8",
            )
            result = db._load_taxa_for_ids(path, {77})[77]
        self.assertEqual(result["inaturalist_id"], "987")
        self.assertEqual(result["inaturalist_url"], "https://www.inaturalist.org/taxa/987")

    def test_incomplete_taxon_rows_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "taxa.csv"
            path.write_text(
                "id,taxonID,scientificName,class,kingdom\n"
                "77,https://www.inaturalist.org/taxa/77,Animalia,Mammalia,Animalia\n"
                "78,https://www.inaturalist.org/taxa/78,Incomplete,,Animalia\n"
                "79,https://www.inaturalist.org/taxa/79,Malformed,Mammalia,Animalia,extra\n",
                encoding="utf-8",
            )
            result = db._load_taxa_for_ids(path, {77, 78, 79})
        self.assertEqual(set(result), {77})


class AnimalImageServiceTests(unittest.TestCase):
    def test_fetches_medium_url_and_caches_image_and_metadata(self) -> None:
        photo = {
            "medium_url": "https://images.example/medium.jpg",
            "square_url": "https://images.example/square.jpg",
            "url": "https://images.example/original.jpg",
            "attribution": "Photo by Ada",
            "license_code": "cc-by-nc",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            service = AnimalImageService(Path(temp_dir))
            with patch(
                "animal_images.urlopen",
                side_effect=[
                    FakeResponse(_taxon_response(photo)),
                    FakeResponse(b"\xff\xd8\xffimage-bytes"),
                ],
            ) as urlopen_mock:
                result = service.get_image("123")
                cached = service.get_image("123")
            self.assertTrue(result.available)
            self.assertEqual(result.image_url, photo["medium_url"])
            self.assertEqual(result.attribution, "Photo by Ada")
            self.assertEqual(result.license_code, "cc-by-nc")
            self.assertEqual(cached, result)
            self.assertEqual(urlopen_mock.call_count, 2)
            self.assertTrue((Path(temp_dir) / "123.jpg").is_file())
            metadata = json.loads((Path(temp_dir) / "123.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["taxon_url"], "https://www.inaturalist.org/taxa/123")
            self.assertEqual(metadata["license_code"], "cc-by-nc")
            service.shutdown()

    def test_default_photo_absence_is_cached(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = AnimalImageService(Path(temp_dir))
            with patch("animal_images.urlopen", return_value=FakeResponse(_taxon_response(None))) as urlopen_mock:
                first = service.get_image("321")
                second = service.get_image("321")
            self.assertFalse(first.available)
            self.assertFalse(second.available)
            self.assertEqual(urlopen_mock.call_count, 1)
            self.assertTrue((Path(temp_dir) / "321.json").is_file())
            service.shutdown()

    def test_invalid_json_and_http_status_fall_back_without_exception(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = AnimalImageService(Path(temp_dir))
            with patch("animal_images.urlopen", return_value=FakeResponse(b"not json")):
                self.assertFalse(service.get_image("10").available)
            with patch("animal_images.urlopen", return_value=FakeResponse(b"", status=503)):
                self.assertFalse(service.get_image("11").available)
            service.shutdown()

    def test_offline_fallback_and_invalid_id_do_not_raise(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = AnimalImageService(Path(temp_dir))
            with patch("animal_images.urlopen", side_effect=URLError("offline")) as urlopen_mock:
                self.assertFalse(service.get_image("22").available)
                invalid = service.get_image(None)
            self.assertFalse(invalid.available)
            self.assertEqual(urlopen_mock.call_count, 1)
            service.shutdown()

    def test_repeated_async_request_reuses_the_same_future(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = AnimalImageService(Path(temp_dir))
            with patch("animal_images.urlopen", return_value=FakeResponse(_taxon_response(None))) as urlopen_mock:
                first = service.request("123")
                second = service.request("123")
                self.assertIs(first, second)
                self.assertFalse(first.result(timeout=2).available)
            self.assertEqual(urlopen_mock.call_count, 1)
            service.shutdown()


class LegacyAnimalRecordTests(unittest.TestCase):
    def test_old_slotted_pickle_defaults_new_fields(self) -> None:
        @dataclass(frozen=True, slots=True)
        class LegacyRecord:
            id: int
            common_name: str
            scientific_name: str
            taxonomic_class: str
            kingdom: str = ""

        LegacyRecord.__module__ = animal.__name__
        LegacyRecord.__name__ = "AnimalRecord"
        LegacyRecord.__qualname__ = "AnimalRecord"
        previous_record = animal.AnimalRecord
        animal.AnimalRecord = LegacyRecord
        try:
            old_pickle = pickle.dumps(LegacyRecord(7, "Animal", "Animal sp.", "Mammalia", "Animalia"))
        finally:
            animal.AnimalRecord = previous_record
        loaded = pickle.loads(old_pickle)
        self.assertIsInstance(loaded, AnimalRecord)
        self.assertIsNone(loaded.inaturalist_id)
        self.assertIsNone(loaded.inaturalist_url)
        self.assertIsNone(loaded.image_url)
        self.assertIsNone(loaded.image_attribution)
        self.assertIsNone(loaded.image_license_code)


if __name__ == "__main__":
    unittest.main()
