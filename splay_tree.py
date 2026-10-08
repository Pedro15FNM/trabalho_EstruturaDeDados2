"""Árvore Splay: BST autoajustável indexada por ID numérico do animal."""
# =========================================================================
# ESTRUTURA: SPLAY TREE (ÁRVORE DE AFUNILAMENTO)
# =========================================================================
# Função e Implementação:
# Atua como o banco de dados primário do jogo em memória, armazenando os 
# objetos 'AnimalRecord' utilizando o ID do animal como chave de busca.
# A sua principal característica matemática é a "Localidade de Referência":
# sempre que um animal é consultado via 'find()', operações de splay 
# (rotações Zig, Zig-Zig e Zig-Zag) movem esse nó específico para a raiz.
#
# Aplicação Prática (Sistema de Raridade / Cache LRU):
# Para justificar o uso desta estrutura em vez de um Array ou Tabela Hash O(1),
# o método 'start_new_turn()' implementa uma mecânica de raridade. 
# Animais de classes comuns (Aves, Mammalia, Reptilia, Amphibia) são 
# sorteados 80% das vezes, enquanto os raros compõem os 20% restantes.
# 
# Como os animais comuns são requisitados o tempo todo, as rotações da Splay 
# Tree os mantêm permanentemente aglomerados no topo da estrutura. Isso 
# transforma a árvore em uma Cache LRU (Least Recently Used) orgânica, 
# tornando a busca pelos alvos mais frequentes extremamente rápida, com
# tempo amortizado muito próximo de O(1).

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, Iterator, TypeVar

T = TypeVar("T")


@dataclass
class SplayNode(Generic[T]):
    """Nó da árvore; chave = ID numérico exclusivo."""

    key: int
    value: T
    left: SplayNode[T] | None = None
    right: SplayNode[T] | None = None
    parent: SplayNode[T] | None = field(default=None, compare=False, repr=False)


class SplayTree(Generic[T]):
    """BST com operação de splay após busca (nó encontrado vai à raiz)."""

    __slots__ = ("root", "_keys_cache")

    def __init__(self) -> None:
        self.root: SplayNode[T] | None = None
        self._keys_cache: list[int] | None = None

    def _invalidate_keys(self) -> None:
        self._keys_cache = None

    def _set_parent(self, node: SplayNode[T] | None, parent: SplayNode[T] | None) -> None:
        if node is not None:
            node.parent = parent

    def _rotate_left(self, x: SplayNode[T]) -> None:
        """Rotação à esquerda em x (filho direito sobe)."""
        y = x.right
        assert y is not None
        x.right = y.left
        if y.left is not None:
            y.left.parent = x
        y.parent = x.parent
        if x.parent is None:
            self.root = y
        elif x is x.parent.left:
            x.parent.left = y
        else:
            x.parent.right = y
        y.left = x
        x.parent = y

    def _rotate_right(self, x: SplayNode[T]) -> None:
        """Rotação à direita em x (filho esquerdo sobe)."""
        y = x.left
        assert y is not None
        x.left = y.right
        if y.right is not None:
            y.right.parent = x
        y.parent = x.parent
        if x.parent is None:
            self.root = y
        elif x is x.parent.left:
            x.parent.left = y
        else:
            x.parent.right = y
        y.right = x
        x.parent = y

    def _splay(self, x: SplayNode[T]) -> None:
        """Move x até a raiz via rotações zig / zig-zig / zig-zag."""
        while x.parent is not None:
            p = x.parent
            g = p.parent
            if g is None:
                if x is p.left:
                    self._rotate_right(p)
                else:
                    self._rotate_left(p)
            elif p is g.left and x is p.left:
                self._rotate_right(g)
                self._rotate_right(p)
            elif p is g.right and x is p.right:
                self._rotate_left(g)
                self._rotate_left(p)
            elif p is g.right and x is p.left:
                self._rotate_right(p)
                self._rotate_left(g)
            else:
                self._rotate_left(p)
                self._rotate_right(g)

    def _search_node(self, key: int) -> SplayNode[T] | None:
        """Busca BST por ID; em sucesso, splay do nó encontrado."""
        cur = self.root
        last: SplayNode[T] | None = None
        while cur is not None:
            last = cur
            if key == cur.key:
                self._splay(cur)
                return cur
            cur = cur.left if key < cur.key else cur.right
        if last is not None:
            self._splay(last)
        return None

    def insert(self, key: int, value: T) -> None:
        """Insere par (ID, valor); chaves devem ser inteiros positivos."""
        if key <= 0:
            raise ValueError(f"Chave inválida: {key}")
        if self.root is None:
            self.root = SplayNode(key, value)
            self._invalidate_keys()
            return
        existing = self._search_node(key)
        if existing is not None:
            existing.value = value
            return
        assert self.root is not None
        new = SplayNode(key, value)
        if key < self.root.key:
            new.left = self.root.left
            new.right = self.root
            self._set_parent(new.left, new)
            self.root.left = None
            self.root.parent = new
        else:
            new.right = self.root.right
            new.left = self.root
            self._set_parent(new.right, new)
            self.root.right = None
            self.root.parent = new
        self.root = new
        new.parent = None
        self._invalidate_keys()

    def find(self, key: int) -> T | None:
        """Busca por ID; após sucesso, o nó fica na raiz."""
        node = self._search_node(key)
        return node.value if node is not None else None

    def delete(self, key: int) -> bool:
        node = self._search_node(key)
        if node is None:
            return False
        if node.left is None:
            self.root = node.right
            self._set_parent(self.root, None)
        elif node.right is None:
            self.root = node.left
            self._set_parent(self.root, None)
        else:
            replacement = node.left
            while replacement.right is not None:
                replacement = replacement.right
            self._splay(replacement)
            replacement.right = node.right
            if node.right is not None:
                node.right.parent = replacement
            self.root = replacement
            replacement.parent = None
        self._invalidate_keys()
        return True

    def search_root_key(self) -> int | None:
        return self.root.key if self.root else None

    def keys_inorder(self) -> list[int]:
        if self._keys_cache is not None:
            return list(self._keys_cache)
        out: list[int] = []
        self._inorder_keys(self.root, out)
        self._keys_cache = out
        return list(out)

    def _inorder_keys(self, node: SplayNode[T] | None, out: list[int]) -> None:
        """Percorre in-order sem recursão (árvores grandes vindas de CSV)."""
        if node is None:
            return
        stack: list[SplayNode[T]] = []
        cur: SplayNode[T] | None = node
        while stack or cur is not None:
            while cur is not None:
                stack.append(cur)
                cur = cur.left
            cur = stack.pop()
            out.append(cur.key)
            cur = cur.right

    def values_inorder(self) -> list[T]:
        if self.root is None:
            return []
        out: list[T] = []
        stack: list[SplayNode[T]] = []
        cur: SplayNode[T] | None = self.root
        while stack or cur is not None:
            while cur is not None:
                stack.append(cur)
                cur = cur.left
            cur = stack.pop()
            out.append(cur.value)
            cur = cur.right
        return out

    def inorder_values(self) -> Iterator[T]:
        yield from self.values_inorder()

    def __len__(self) -> int:
        if self._keys_cache is not None:
            return len(self._keys_cache)
        return len(self.keys_inorder())
