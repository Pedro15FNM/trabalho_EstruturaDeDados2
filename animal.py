"""Modelo de registro de animal (independente de Pygame e estruturas de dados)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AnimalRecord:
    """Animal indexado pela Splay Tree (chave = id numérico do taxon)."""

    id: int
    common_name: str
    scientific_name: str
    taxonomic_class: str
    kingdom: str = ""
    inaturalist_id: str | None = None
    inaturalist_url: str | None = None
    image_url: str | None = None
    image_attribution: str | None = None
    image_license_code: str | None = None

    def __post_init__(self) -> None:
        if self.id <= 0:
            raise ValueError(f"ID inválido: {self.id}")
        if not self.taxonomic_class.strip():
            raise ValueError(f"Classe taxonômica vazia para id={self.id}")

    def __getattr__(self, name: str) -> None:
        if name in {
            "inaturalist_id",
            "inaturalist_url",
            "image_url",
            "image_attribution",
            "image_license_code",
        }:
            return None
        raise AttributeError(name)
