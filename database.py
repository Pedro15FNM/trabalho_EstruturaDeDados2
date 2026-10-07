"""Leitura de CSV iNaturalist, construção da Splay Tree e cache em pickle.

Cabeçalhos reais:

VernacularNames-portuguese.csv
  id, vernacularName, language, locality, countryCode, source, lexicon, contributor, created

taxa.csv
  id, taxonID, identifier, parentNameUsageID, kingdom, phylum, class, order, family,
  genus, specificEpithet, infraspecificEpithet, modified, scientificName, taxonRank, references
"""

from __future__ import annotations

import csv
import hashlib
import random
from pathlib import Path
from typing import Iterable

from animal import AnimalRecord
from animal_images import extract_inaturalist_id, inaturalist_taxon_url
from splay_tree import SplayTree
from tree_persistence import DEFAULT_PICKLE_PATH, load_splay_tree, save_splay_tree

DATA_DIR = Path(__file__).resolve().parent / "data"
VERNACULAR_CSV = DATA_DIR / "VernacularNames-portuguese.csv"
TAXA_CSV = DATA_DIR / "taxa.csv"
PICKLE_PATH = DEFAULT_PICKLE_PATH

# Limite opcional para desenvolvimento (None = todos os nomes vernáculos)
MAX_VERNACULAR_ROWS: int | None = None

# Ordem de inserção na Splay Tree (evita BST degenerada por IDs crescentes)
INSERT_SHUFFLE_SEED = 42


class DatabaseError(Exception):
    """Erro fatal ao montar a base de animais."""


def _normalize_fieldnames(fieldnames: list[str] | None) -> dict[str, str]:
    if not fieldnames:
        return {}
    return {h.strip().lower(): h for h in fieldnames}


def _file_fingerprint(paths: Iterable[Path]) -> str:
    parts: list[str] = [
        f"max_rows={MAX_VERNACULAR_ROWS}",
        f"shuffle_seed={INSERT_SHUFFLE_SEED}",
        "animal_schema=2",
    ]
    for path in paths:
        p = str(path.resolve())
        if path.is_file():
            st = path.stat()
            parts.append(f"{p}:{st.st_mtime_ns}:{st.st_size}")
        else:
            parts.append(f"{p}:missing")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _load_vernacular_names(path: Path) -> dict[int, str]:
    """Mapa taxon id → nome popular (português); preferência por nome mais longo."""
    if not path.is_file():
        raise DatabaseError(f"CSV não encontrado: {path}")
    names: dict[int, str] = {}
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        fields = _normalize_fieldnames(reader.fieldnames)
        id_col = fields.get("id")
        name_col = fields.get("vernacularname")
        if not id_col or not name_col:
            raise DatabaseError(
                f"Cabeçalhos esperados id, vernacularName em {path}; obtido {reader.fieldnames}"
            )
        for n, row in enumerate(reader, start=1):
            if MAX_VERNACULAR_ROWS is not None and n > MAX_VERNACULAR_ROWS:
                break
            raw_id = (row.get(id_col) or "").strip()
            raw_name = (row.get(name_col) or "").strip()
            if not raw_id or not raw_name:
                continue
            try:
                taxon_id = int(raw_id)
            except ValueError:
                continue
            if taxon_id <= 0:
                continue
            if taxon_id not in names or len(raw_name) > len(names[taxon_id]):
                names[taxon_id] = raw_name
    if not names:
        raise DatabaseError(f"Nenhum nome vernáculo válido em {path}")
    return names


def _load_taxa_for_ids(path: Path, ids: set[int]) -> dict[int, dict[str, str]]:
    """Metadados taxonômicos para os IDs pedidos (varredura única de taxa.csv)."""
    if not path.is_file():
        raise DatabaseError(f"CSV não encontrado: {path}")
    found: dict[int, dict[str, str]] = {}
    remaining = set(ids)
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise DatabaseError(f"CSV vazio ou sem cabeçalho: {path}")
        fields = _normalize_fieldnames(reader.fieldnames)
        id_col = fields.get("id", "id")
        class_col = fields.get("class", "class")
        sci_col = fields.get("scientificname", "scientificName")
        kingdom_col = fields.get("kingdom", "kingdom")
        taxon_id_col = fields.get("taxonid")
        identifier_col = fields.get("identifier")
        rank_col = fields.get("taxonrank")
        for row in reader:
            if None in row:
                continue
            raw_id = (row.get(id_col) or "").strip()
            if not raw_id:
                continue
            try:
                tid = int(raw_id)
            except ValueError:
                continue
            if tid not in remaining:
                continue
            tax_class = (row.get(class_col) or "").strip()
            scientific_name = (row.get(sci_col) or "").strip()
            kingdom = (row.get(kingdom_col) or "").strip()
            if not tax_class or not scientific_name or not kingdom:
                continue
            inaturalist_id = extract_inaturalist_id(
                row.get(taxon_id_col) if taxon_id_col else None
            ) or extract_inaturalist_id(
                row.get(identifier_col) if identifier_col else None
            )
            found[tid] = {
                "scientific_name": scientific_name,
                "taxonomic_class": tax_class,
                "kingdom": kingdom,
                "inaturalist_id": inaturalist_id or "",
                "inaturalist_url": inaturalist_taxon_url(inaturalist_id) or "",
                "taxon_rank": (row.get(rank_col) or "").strip() if rank_col else "",
            }
            remaining.discard(tid)
            if not remaining:
                break
    return found


def build_tree_from_csv(*, shuffle_seed: int | None = INSERT_SHUFFLE_SEED) -> SplayTree[AnimalRecord]:
    vernacular = _load_vernacular_names(VERNACULAR_CSV)
    taxa = _load_taxa_for_ids(TAXA_CSV, set(vernacular.keys()))
    pairs = list(vernacular.items())
    if shuffle_seed is not None:
        random.Random(shuffle_seed).shuffle(pairs)
    tree: SplayTree[AnimalRecord] = SplayTree()
    for taxon_id, common in pairs:
        meta = taxa.get(taxon_id)
        if meta is None:
            continue
        try:
            record = AnimalRecord(
                id=taxon_id,
                common_name=common,
                scientific_name=meta["scientific_name"],
                taxonomic_class=meta["taxonomic_class"],
                kingdom=meta.get("kingdom", ""),
                inaturalist_id=meta.get("inaturalist_id") or None,
                inaturalist_url=meta.get("inaturalist_url") or None,
            )
        except ValueError:
            continue
        tree.insert(taxon_id, record)
    if len(tree) == 0:
        raise DatabaseError("Nenhum animal válido após cruzar vernáculos com taxa.csv")
    return tree


def find_animal_by_id(tree: SplayTree[AnimalRecord], animal_id: int) -> AnimalRecord | None:
    """Busca animal pelo ID; executa splay e deixa o nó na raiz se existir."""
    return tree.find(animal_id)


def get_valid_id(tree: SplayTree[AnimalRecord], *, index: int = 0) -> int:
    """Retorna um ID garantidamente presente na árvore (ordem in-order)."""
    keys = tree.keys_inorder()
    if not keys:
        raise DatabaseError("Splay Tree vazia: nenhum ID disponível.")
    if index < 0 or index >= len(keys):
        raise DatabaseError(f"Índice fora do intervalo: {index} (tamanho {len(keys)})")
    return keys[index]


def load_animal_tree(*, force_rebuild: bool = False) -> SplayTree[AnimalRecord]:
    """
    Obtém a Splay Tree de animais:
    1) cache pickle válido em data/animals_splay.pkl;
    2) senão, reconstrói dos CSVs e tenta salvar o cache.
    Falhas de leitura/gravação do pickle não interrompem o fluxo.
    """
    fingerprint = _file_fingerprint([VERNACULAR_CSV, TAXA_CSV])
    if not force_rebuild:
        cached = load_splay_tree(fingerprint, PICKLE_PATH)
        if cached is not None:
            return cached
    tree = build_tree_from_csv()
    save_splay_tree(tree, fingerprint, PICKLE_PATH)
    return tree


_FAKE_CLASSES = (
    "Aves",
    "Mammalia",
    "Reptilia",
    "Amphibia",
    "Actinopterygii",
    "Insecta",
    "Arachnida",
    "Mollusca",
)


def build_fake_tree(n: int, rng: random.Random) -> SplayTree[AnimalRecord]:
    """Base sintética para testes de estresse (--fake)."""
    iconic = list(_FAKE_CLASSES)
    tree: SplayTree[AnimalRecord] = SplayTree()
    key = 0
    for i in range(n):
        key += rng.randint(1, 50)
        tax_class = rng.choice(iconic)
        rec = AnimalRecord(
            id=key,
            common_name=f"Animal {i}",
            scientific_name=f"Fictus sp.{i}",
            taxonomic_class=tax_class,
            kingdom="Animalia",
        )
        tree.insert(key, rec)
    return tree


def all_taxonomic_classes(tree: SplayTree[AnimalRecord]) -> set[str]:
    return {rec.taxonomic_class for rec in tree.values_inorder()}
