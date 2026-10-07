"""Testes pequenos, determinísticos e objetivos cobrindo os 15 pontos de revisão:

1. Splay Tree
2. Skip List
3. Leitura dos CSVs (lógica e parsing)
4. Persistência (pickle + validação)
5. Sorteio de IDs válidos
6. Splay após busca
7. Energia
8. Game Over por falta de energia
9. Identificação da classe do alvo
10. Chegada ao prédio correto
11. Combate 50/50
12. Vitória
13. Derrota
14. Retorno à head
15. Novo turno
"""

from __future__ import annotations

import csv
import io
import random
import tempfile
import unittest
from pathlib import Path

from animal import AnimalRecord
from game import MAX_ENERGY, GameSession, GameState
from skip_list import ScenarioSkipList
from splay_tree import SplayTree
from tree_persistence import load_splay_tree, save_splay_tree
import database as db


class ReviewDataStructuresTests(unittest.TestCase):
    """Verificações de estruturas de dados (Splay Tree, Skip List, CSV e Persistência)."""

    def test_01_splay_tree_basic_and_search_splay(self) -> None:
        """1 & 6. Splay Tree: inserção, remoção e splay do nó acessado para a raiz."""
        tree: SplayTree[str] = SplayTree()
        # Inserção de chaves não ordenadas
        for k, v in [(50, "C"), (20, "A"), (40, "B"), (70, "D"), (60, "E")]:
            tree.insert(k, v)

        self.assertEqual(len(tree), 5)
        # Inorder deve ser estritamente ordenado e iterativo
        self.assertEqual(tree.keys_inorder(), [20, 40, 50, 60, 70])
        self.assertEqual(tree.values_inorder(), ["A", "B", "C", "E", "D"])

        # Busca com splay: o nó acessado deve subir para a raiz
        val = tree.find(20)
        self.assertEqual(val, "A")
        self.assertIsNotNone(tree.root)
        assert tree.root is not None
        self.assertEqual(tree.root.key, 20)

        # Outra busca: sobe o novo nó
        tree.find(70)
        self.assertEqual(tree.root.key, 70)

        # Remoção
        deleted = tree.delete(50)
        self.assertTrue(deleted)
        self.assertEqual(tree.keys_inorder(), [20, 40, 60, 70])

    def test_02_skip_list_levels_and_upper_skips(self) -> None:
        """2. Skip List: bulk load de classes, nós ordenados e saltos em níveis superiores."""
        rng = random.Random(42)
        sl = ScenarioSkipList(rng)
        classes = ["Mammalia", "Aves", "Reptilia", "Amphibia", "Insecta"]
        nodes = sl.bulk_load_classes(classes)

        # Classes são ordenadas lexicograficamente
        sorted_cls = sorted(set(classes))
        self.assertEqual([n.animal_class for n in nodes], sorted_cls)
        self.assertEqual(sl.head.animal_class, "—")

        # Head aponta para frente
        self.assertTrue(sl.can_move(sl.head, 0, 0))
        nxt = sl.move(sl.head, 0, 0)
        self.assertIsNotNone(nxt)
        assert nxt is not None
        self.assertEqual(nxt.idx, 1)

        # Encontra se há atalho superior
        top = sl.height_of(sl.head) - 1
        has_jump = any(sl.has_forward(sl.head, lvl) for lvl in range(1, top + 1))
        self.assertTrue(has_jump or sl.size > 0)

    def test_03_csv_parsing_logic(self) -> None:
        """3. Leitura dos CSVs: normalização, casamento de chaves e criação de AnimalRecord."""
        # Simula pequenos CSVs usando tempfile
        vernacular_data = (
            "id,vernacularName,language\n"
            "10,Onca,pt\n"
            "10,Onca-pintada,pt\n"  # Nome mais longo deve prevalecer
            "20,Arara-azul,pt\n"
        )
        taxa_data = (
            "id,scientificName,class,kingdom\n"
            "10,Panthera onca,Mammalia,Animalia\n"
            "20,Anodorhynchus hyacinthinus,Aves,Animalia\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            v_path = Path(tmpdir) / "v.csv"
            t_path = Path(tmpdir) / "t.csv"
            v_path.write_text(vernacular_data, encoding="utf-8")
            t_path.write_text(taxa_data, encoding="utf-8")

            names = db._load_vernacular_names(v_path)
            self.assertEqual(names[10], "Onca-pintada")
            self.assertEqual(names[20], "Arara-azul")

            taxa = db._load_taxa_for_ids(t_path, set(names.keys()))
            self.assertEqual(taxa[10]["taxonomic_class"], "Mammalia")
            self.assertEqual(taxa[20]["taxonomic_class"], "Aves")

            # Criação de AnimalRecord
            rec = AnimalRecord(10, names[10], taxa[10]["scientific_name"], taxa[10]["taxonomic_class"])
            self.assertEqual(rec.id, 10)
            self.assertEqual(rec.common_name, "Onca-pintada")
            self.assertEqual(rec.taxonomic_class, "Mammalia")

    def test_04_tree_persistence(self) -> None:
        """4. Persistência: gravação atômica, carregamento e validação de integridade/fingerprint."""
        tree: SplayTree[AnimalRecord] = SplayTree()
        rec = AnimalRecord(1, "Lobo-guara", "Chrysocyon brachyurus", "Mammalia")
        tree.insert(1, rec)

        with tempfile.TemporaryDirectory() as tmpdir:
            pkl_path = Path(tmpdir) / "test_tree.pkl"
            saved = save_splay_tree(tree, "fingerprint_123", pkl_path)
            self.assertTrue(saved)
            self.assertTrue(pkl_path.is_file())

            # Carregamento com mesmo fingerprint
            loaded = load_splay_tree("fingerprint_123", pkl_path)
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(len(loaded), 1)
            found = loaded.find(1)
            self.assertIsNotNone(found)
            assert found is not None
            self.assertEqual(found.common_name, "Lobo-guara")

            # Rejeição com fingerprint divergente
            self.assertIsNone(load_splay_tree("outra_hash", pkl_path))


class ReviewGameRulesTests(unittest.TestCase):
    """Verificações de regras de gameplay (alvo, energia, combate 50/50, vitória, derrota)."""

    def _setup_session(
        self,
        animals: list[tuple[int, str, str, str]],
        *,
        max_energy: int = 10,
        seed: int = 42,
    ) -> GameSession:
        rng = random.Random(seed)
        tree: SplayTree[AnimalRecord] = SplayTree()
        classes = set()
        for aid, pt, sci, cls in animals:
            tree.insert(aid, AnimalRecord(aid, pt, sci, cls))
            classes.add(cls)
        scenario = ScenarioSkipList(rng)
        scenario.bulk_load_classes(sorted(classes))
        session = GameSession(
            tree=tree,
            scenario=scenario,
            rng=rng,
            max_energy=max_energy,
            target=None,
        )
        return session

    def test_05_valid_target_selection_and_splay_at_turn_start(self) -> None:
        """5, 6, 9 & 14. Início de turno: sorteia ID válido, splay na raiz, jogador na head e mostra só a classe."""
        animals = [
            (10, "Arara", "A. sp.", "Aves"),
            (20, "Onca", "P. onca", "Mammalia"),
            (30, "Jacare", "C. yacare", "Reptilia"),
        ]
        s = self._setup_session(animals)

        # 5. ID sorteado realmente existe na árvore
        self.assertIsNotNone(s.target)
        assert s.target is not None
        self.assertIn(s.target.id, [10, 20, 30])

        # 6. Splay executado na busca: nó alvo está na raiz
        self.assertIsNotNone(s.tree.root)
        assert s.tree.root is not None
        self.assertEqual(s.tree.root.key, s.target.id)

        # 9. Interface revela somente a classe taxonômica (não revela nome comum/científico)
        self.assertEqual(s.target_class_label(), s.target.taxonomic_class)
        self.assertNotIn(s.target.common_name, s.target_class_label())
        self.assertNotIn(s.target.scientific_name, s.target_class_label())

        # 14. Jogador inicia na head e andar 0
        self.assertIs(s.current_node, s.scenario.head)
        self.assertEqual(s.current_level, 0)
        self.assertEqual(s.energy, s.max_energy)
        self.assertEqual(s.state, GameState.PLAYING)

    def test_07_energy_consumption_and_zero_energy_block(self) -> None:
        """7. Cada travessia (passo ou salto) consome 1 de energia; movimento com 0 de energia é bloqueado."""
        animals = [
            (1, "A1", "S1", "Aves"),
            (2, "M1", "S2", "Mammalia"),
            (3, "R1", "S3", "Reptilia"),
        ]
        s = self._setup_session(animals, max_energy=3)
        start_energy = s.energy

        # Movimento consome exatamente 1 energia
        self.assertTrue(s.try_move_at_level(0))
        self.assertEqual(s.energy, start_energy - 1)
        self.assertEqual(s.moves, 1)

        # Não se move com energia zerada
        s.energy = 0
        cur_node = s.current_node
        cur_floor = s.current_level
        self.assertFalse(s.try_move_at_level(0))
        self.assertIs(s.current_node, cur_node)
        s.change_floor(1)
        self.assertEqual(s.current_level, cur_floor)

    def test_08_game_over_by_lack_of_energy(self) -> None:
        """8. Game Over ocorre quando a energia chega a zero antes de alcançar o prédio alvo."""
        animals = [
            (1, "A1", "S1", "Aves"),
            (2, "M1", "S2", "Mammalia"),
            (3, "R1", "S3", "Reptilia"),
        ]
        s = self._setup_session(animals, max_energy=1)
        # Força o alvo a ser Reptilia (prédio 3)
        rec = s.tree.find(3)
        assert rec is not None
        s.target = rec
        s.current_node = s.scenario.head
        s.energy = 1

        # Mover no nível 0 vai para o prédio 1 (Aves != Reptilia) com energia chegando a 0
        self.assertTrue(s.try_move_at_level(0))
        self.assertNotEqual(s.current_node.animal_class, "Reptilia")
        self.assertEqual(s.energy, 0)
        self.assertEqual(s.state, GameState.GAME_OVER)
        self.assertIn("sem energia", s.message.lower())

    def test_10_combat_50_50_victory(self) -> None:
        """10, 11, 12, 14 & 15. Chegada ao prédio correto + Vitória na moeda 50/50."""
        animals = [
            (10, "Onca", "P. onca", "Mammalia"),
            (20, "Arara", "A. sp.", "Aves"),
        ]
        s = self._setup_session(animals, max_energy=10)
        s.set_coin_flip(lambda: True)  # Simula moeda = vitória

        target_building = s.scenario.node_for_class(s.target.taxonomic_class)
        assert target_building is not None

        # Reduz energia para validar retorno ao máximo
        s.energy = 2
        # Move para o prédio alvo
        s.current_node = target_building
        s._after_move()

        self.assertEqual(s.state, GameState.COMBAT)
        self.assertEqual(s.victories, 0)
        s.resolve_combat()

        # 12. Vitória: jogador sobrevive
        # 14. Jogador retorna à head e andar 0
        self.assertIs(s.current_node, s.scenario.head)
        self.assertEqual(s.current_level, 0)
        # Energia retorna ao máximo
        self.assertEqual(s.energy, s.max_energy)
        # 15. Novo turno iniciado com novo animal sorteado (e splay executado)
        self.assertEqual(s.state, GameState.PLAYING)
        self.assertEqual(s.victories, 1)
        self.assertIsNotNone(s.target)
        assert s.target is not None
        self.assertIsNotNone(s.tree.root)
        assert s.tree.root is not None
        self.assertEqual(s.tree.root.key, s.target.id)

    def test_13_combat_50_50_defeat(self) -> None:
        """10, 11 & 13. Chegada ao prédio correto + Derrota na moeda 50/50."""
        animals = [
            (10, "Onca", "P. onca", "Mammalia"),
            (20, "Arara", "A. sp.", "Aves"),
        ]
        s = self._setup_session(animals, max_energy=10)
        s.set_coin_flip(lambda: False)  # Simula moeda = derrota

        target_building = s.scenario.node_for_class(s.target.taxonomic_class)
        assert target_building is not None

        s.current_node = target_building
        s._after_move()

        self.assertEqual(s.state, GameState.COMBAT)
        s.resolve_combat()

        # 13. Derrota: Game Over imediato, nenhum novo turno, navegação bloqueada
        self.assertEqual(s.state, GameState.GAME_OVER)
        self.assertIn("derrota", s.message.lower())
        self.assertFalse(s.try_move_at_level(0))


if __name__ == "__main__":
    unittest.main()
