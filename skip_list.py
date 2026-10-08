"""Skip List do cenário: cada nó é um prédio associado a uma classe taxonômica."""
# =========================================================================
    # ESTRUTURA: SKIP LIST (CENÁRIO 2D PROBABILÍSTICO)
    # =========================================================================
    # Função e Implementação:
    # A Skip List foi adaptada de um algoritmo de busca O(log n) para servir 
    # como a topologia física (o mapa/cenário de plataformas) do jogo.
    # 
    # Em vez de armazenar milhares de animais individuais, o agrupamento é mais 
    # restrito: cada nó inserido na Skip List representa uma Classe Taxonômica 
    # única (ordenada alfabeticamente).
    #
    # Anatomia da Estrutura no Jogo:
    # - Prédios (Nós): Cada nó vira um edifício no mapa.
    # - Andares (Níveis): O nível probabilístico que o algoritmo sorteia para  
    #   cada nó determina exatamente a quantidade de andares daquele edifício.
    # - Tirolesas (Ponteiros Forward): Os arrays de ponteiros que apontam 
    #   para a frente são renderizados visualmente como as tirolesas.
    #
    # Modificação da Busca Clássica:
    # A pesquisa algorítmica linear nativa da estrutura foi propositalmente 
    # removida. A travessia de nós é feita de forma 100% manual pelo jogador, 
    # onde cada ponteiro 'forward' atravessado exige o gasto de 1 ponto de energia.

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Sequence

# Parâmetros compartilhados com a UI (importados de config em runtime se necessário)
SKIP_P = 0.5
MAX_LEVEL = 12


@dataclass
class BuildingNode:
    """Prédio do cenário; `animal_class` é a classe taxonômica daquele prédio."""

    idx: int
    name: str
    animal_class: str
    level: int
    forward: list[BuildingNode | None] = field(default_factory=list)
    color: tuple[int, int, int] = (120, 120, 140)

    @property
    def key(self) -> str:
        return self.animal_class


class ScenarioSkipList:
    """Skip list para navegação; travessia apenas via métodos públicos."""

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.head = BuildingNode(0, "INÍCIO", "—", MAX_LEVEL)
        self.head.forward = [None] * MAX_LEVEL
        self.head.color = (90, 100, 130)
        self.level = 1
        self.size = 0
        self._nodes: list[BuildingNode] = []
        self._class_to_node: dict[str, BuildingNode] = {}

    def _random_level(self) -> int:
        lvl = 1
        while lvl < MAX_LEVEL and self.rng.random() < SKIP_P:
            lvl += 1
        return lvl

    def bulk_load_classes(self, classes: Sequence[str]) -> list[BuildingNode]:
        """Carga O(n) em lote (classes já ordenadas)."""
        sorted_classes = sorted(set(c.strip() for c in classes if c.strip()))
        tails: list[BuildingNode] = [self.head] * MAX_LEVEL
        nodes: list[BuildingNode] = []
        self._class_to_node.clear()
        for i, animal_class in enumerate(sorted_classes, start=1):
            node = BuildingNode(
                i,
                animal_class,
                animal_class,
                self._random_level(),
            )
            node.forward = [None] * node.level
            for lvl in range(node.level):
                tails[lvl].forward[lvl] = node
                tails[lvl] = node
            if node.level > self.level:
                self.level = node.level
            nodes.append(node)
            self._class_to_node[animal_class] = node
        self._nodes = nodes
        self.size = len(nodes)
        return nodes

    def node_for_class(self, animal_class: str) -> BuildingNode | None:
        return self._class_to_node.get(animal_class)

    def classes_present(self) -> frozenset[str]:
        return frozenset(self._class_to_node.keys())

    @property
    def buildings(self) -> list[BuildingNode]:
        return list(self._nodes)

    def height_of(self, node: BuildingNode) -> int:
        return self.level if node is self.head else node.level

    def _next_at(self, node: BuildingNode, level: int) -> BuildingNode | None:
        if level < 0 or level >= len(node.forward):
            return None
        return node.forward[level]

    def has_forward(self, node: BuildingNode, level: int) -> bool:
        return self._next_at(node, level) is not None

    def can_move(self, current: BuildingNode, current_level: int, level: int) -> bool:
        if level < 0 or level >= self.height_of(current):
            return False
        return self._next_at(current, level) is not None

    def move(self, current: BuildingNode, current_level: int, level: int) -> BuildingNode | None:
        """Avança um ponteiro no nível indicado (1 unidade de energia no jogo)."""
        if not self.can_move(current, current_level, level):
            return None
        nxt = self._next_at(current, level)
        assert nxt is not None
        return nxt

    def get_available_moves(self, current: BuildingNode, current_level: int) -> list[tuple[int, BuildingNode]]:
        top = self.height_of(current) - 1
        out: list[tuple[int, BuildingNode]] = []
        for lvl in range(top + 1):
            nxt = self._next_at(current, lvl)
            if nxt is not None:
                out.append((lvl, nxt))
        return out

    def scan_window(
        self, lo: int, hi: int
    ) -> tuple[list[BuildingNode], list[tuple[BuildingNode, int, BuildingNode]]]:
        """Culling para renderização (mesma ideia do MVP original)."""
        buildings: list[BuildingNode] = []
        edges: list[tuple[BuildingNode, int, BuildingNode]] = []
        x = self.head
        for lvl in range(self.level - 1, -1, -1):
            while x.forward[lvl] is not None and x.forward[lvl].idx < lo:
                x = x.forward[lvl]  # type: ignore[assignment]
            n = x
            while n is not None and n.idx <= hi:
                nxt = n.forward[lvl] if lvl < len(n.forward) else None
                if nxt is not None:
                    edges.append((n, lvl, nxt))
                if lvl == 0 and n.idx >= lo:
                    buildings.append(n)
                n = nxt
        return buildings, edges
