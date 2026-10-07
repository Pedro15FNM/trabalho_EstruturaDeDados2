import random
import unittest

from animal import AnimalRecord
from game import MAX_ENERGY, GameSession, GameState
from skip_list import ScenarioSkipList
from splay_tree import SplayTree


def _make_session_multi(
    animals: list[tuple[int, str, str, str]],
    *,
    extra_classes: list[str] | None = None,
    max_energy: int = MAX_ENERGY,
    seed: int = 1,
) -> GameSession:
    rng = random.Random(seed)
    tree: SplayTree[AnimalRecord] = SplayTree()
    classes = set(extra_classes or [])
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


def _make_session(
    classes: list[str],
    target_class: str,
    *,
    max_energy: int = MAX_ENERGY,
    seed: int = 1,
) -> GameSession:
    return _make_session_multi(
        [(100, "Animal Teste", "Testus sp.", target_class)],
        extra_classes=classes,
        max_energy=max_energy,
        seed=seed,
    )


class GameplayTests(unittest.TestCase):
    def test_target_selection_and_splay_execution(self) -> None:
        """No início de cada turno: escolhe ID existente, busca, executa splay, obtém animal, mostra só classe."""
        animals = [
            (10, "Arara-azul", "Anodorhynchus hyacinthinus", "Aves"),
            (20, "Onça-pintada", "Panthera onca", "Mammalia"),
            (30, "Jacaré-do-pantanal", "Caiman yacare", "Reptilia"),
        ]
        s = _make_session_multi(animals, seed=42)

        # 1. ID escolhido realmente existe na Splay Tree
        self.assertIsNotNone(s.target)
        assert s.target is not None
        self.assertIn(s.target.id, [10, 20, 30])

        # 2 e 3. Splay executado: o nó do animal alvo deve estar na raiz da árvore
        self.assertIsNotNone(s.tree.root)
        assert s.tree.root is not None
        self.assertEqual(s.tree.root.key, s.target.id)

        # 4. Animal obtido
        self.assertIsInstance(s.target, AnimalRecord)

        # 5. Interface expõe apenas a classe taxonômica, sem revelar nome comum ou científico
        self.assertEqual(s.target_class_label(), s.target.taxonomic_class)
        self.assertNotIn(s.target.common_name, s.target_class_label())
        self.assertNotIn(s.target.scientific_name, s.target_class_label())

        # Jogador inicia na head
        self.assertIs(s.current_node, s.scenario.head)
        self.assertEqual(s.current_level, 0)
        self.assertEqual(s.energy, s.max_energy)
        self.assertEqual(s.state, GameState.PLAYING)

    def test_combat_win_restores_energy_and_starts_new_turn_at_head(self) -> None:
        """Vitória no combate: sobrevive, energia volta ao máximo, retorna à head, novo alvo sorteado, novo turno."""
        animals = [
            (10, "Arara-azul", "Anodorhynchus hyacinthinus", "Aves"),
            (20, "Onça-pintada", "Panthera onca", "Mammalia"),
        ]
        s = _make_session_multi(animals, max_energy=10, seed=1)
        s.set_coin_flip(lambda: True)  # Sempre vitória na moeda

        target_class = s.target.taxonomic_class if s.target else ""

        # Encontra o prédio correspondente à classe do alvo
        target_building = s.scenario.node_for_class(target_class)
        self.assertIsNotNone(target_building)
        assert target_building is not None

        # Reduz energia para testar que retorna ao máximo na vitória
        s.energy = 3

        # Atravessa até o prédio do alvo
        s.current_node = target_building
        s._after_move()

        # Chegar ao prédio abre o combate, sem jogar a moeda automaticamente.
        self.assertEqual(s.state, GameState.COMBAT)
        self.assertEqual(s.victories, 0)
        self.assertTrue(s.resolve_combat())

        # Vitória!
        # - jogador sobrevive e começa novo turno
        self.assertEqual(s.state, GameState.PLAYING)
        # - energia retorna ao máximo
        self.assertEqual(s.energy, s.max_energy)
        # - jogador retorna à head
        self.assertIs(s.current_node, s.scenario.head)
        self.assertEqual(s.current_level, 0)
        # - vitórias incrementadas
        self.assertEqual(s.victories, 1)
        # - novo splay executado para o novo alvo
        self.assertIsNotNone(s.target)
        assert s.target is not None
        assert s.tree.root is not None
        self.assertEqual(s.tree.root.key, s.target.id)

    def test_combat_defeat_causes_immediate_game_over(self) -> None:
        """Derrota no combate: jogador morre, Game Over imediato, nenhum novo turno."""
        animals = [
            (10, "Arara-azul", "Anodorhynchus hyacinthinus", "Aves"),
            (20, "Onça-pintada", "Panthera onca", "Mammalia"),
        ]
        s = _make_session_multi(animals, max_energy=10, seed=1)
        s.set_coin_flip(lambda: False)  # Sempre derrota na moeda

        target_class = s.target.taxonomic_class if s.target else ""
        target_building = s.scenario.node_for_class(target_class)
        assert target_building is not None

        s.current_node = target_building
        s._after_move()

        self.assertEqual(s.state, GameState.COMBAT)
        self.assertTrue(s.resolve_combat())

        # Derrota:
        # - Game Over imediato
        self.assertEqual(s.state, GameState.GAME_OVER)
        self.assertIn("derrota", s.message.lower())
        # - nenhum novo turno (continua Game Over, jogador permanece morto)
        self.assertNotEqual(s.state, GameState.PLAYING)

        # Não deve ser possível movimentar-se após Game Over
        self.assertFalse(s.try_move_at_level(0))

    def test_navigation_consumes_energy_and_triggers_combat_on_target_arrival(self) -> None:
        """Navega pela Skip List: consome 1 energia e aciona combate ao chegar no prédio da classe certa."""
        s = _make_session(["Aves", "Mammalia"], "Aves", max_energy=10)
        s.set_coin_flip(lambda: True)

        # Passo da head até o prédio 1 ('Aves') no nível 0
        start_energy = s.energy
        moved = s.try_move_at_level(0)
        self.assertTrue(moved)
        # O prédio correto abre o painel de combate até o jogador confirmar.
        self.assertEqual(s.state, GameState.COMBAT)
        self.assertEqual(s.victories, 0)
        s.resolve_combat()
        self.assertEqual(s.victories, 1)
        self.assertEqual(s.state, GameState.PLAYING)
        self.assertIs(s.current_node, s.scenario.head)
        self.assertEqual(s.energy, s.max_energy)

    def test_configurable_max_energy(self) -> None:
        """A energia máxima deve ser configurável."""
        s15 = _make_session(["Aves", "Mammalia"], "Mammalia", max_energy=15)
        self.assertEqual(s15.max_energy, 15)
        self.assertEqual(s15.energy, 15)

        s5 = _make_session(["Aves", "Mammalia"], "Mammalia", max_energy=5)
        self.assertEqual(s5.max_energy, 5)
        self.assertEqual(s5.energy, 5)

        s5.energy = 2
        s5.restart_turn()
        self.assertEqual(s5.energy, 5)

    def test_upper_level_jump_consumes_only_one_energy(self) -> None:
        """Salto por nível superior consome apenas 1 energia mesmo ignorando vários prédios."""
        found_jump = False
        for seed in range(30):
            s = _make_session(
                ["Aves", "Insecta", "Mammalia", "Plantae", "Reptilia"],
                "Reptilia",
                max_energy=10,
                seed=seed,
            )
            head = s.scenario.head
            top = s.scenario.height_of(head) - 1
            for lvl in range(1, top + 1):
                nxt = s.scenario.move(head, 0, lvl)
                if nxt is not None and nxt.idx > 1 and nxt.animal_class != "Reptilia":
                    start_energy = s.energy
                    moved = s.try_move_at_level(lvl)
                    self.assertTrue(moved)
                    self.assertGreater(s.current_node.idx, 1)
                    self.assertEqual(s.energy, start_energy - 1)
                    found_jump = True
                    break
            if found_jump:
                break
        self.assertTrue(found_jump)

    def test_game_over_when_energy_zero_before_target(self) -> None:
        """Quando a energia chega a zero antes do prédio alvo, ocorre Game Over."""
        s = _make_session(["Aves", "Mammalia", "Reptilia"], "Reptilia", max_energy=1)
        self.assertEqual(s.energy, 1)
        # Prédio 1 é 'Aves', alvo é 'Reptilia'
        moved = s.try_move_at_level(0)
        self.assertTrue(moved)
        self.assertEqual(s.current_node.animal_class, "Aves")
        self.assertEqual(s.energy, 0)
        self.assertEqual(s.state, GameState.GAME_OVER)
        self.assertIn("sem energia", s.message.lower())

    def test_restart_during_combat_keeps_target(self) -> None:
        s = _make_session(["Aves", "Mammalia"], "Aves")
        target = s.target
        building = s.scenario.node_for_class(target.taxonomic_class)
        assert building is not None
        s.current_node = building
        s._after_move()
        self.assertEqual(s.state, GameState.COMBAT)

        s.restart_turn()

        self.assertEqual(s.state, GameState.PLAYING)
        self.assertIs(s.target, target)
        self.assertIs(s.current_node, s.scenario.head)

    def test_new_target_leaves_combat_and_selects_another_animal(self) -> None:
        s = _make_session_multi(
            [(10, "Arara", "A. sp.", "Aves"), (20, "Onça", "P. onca", "Mammalia")],
            seed=7,
        )
        old_target = s.target
        s._id_keys = [old_target.id, 20 if old_target.id == 10 else 10]

        class NextChoice:
            def choice(self, values: list[int]) -> int:
                return next(value for value in values if value != old_target.id)

        s.rng = NextChoice()
        target_building = s.scenario.node_for_class(old_target.taxonomic_class)
        assert target_building is not None
        s.current_node = target_building
        s._after_move()
        s.new_target()

        self.assertEqual(s.state, GameState.PLAYING)
        self.assertNotEqual(s.target.id, old_target.id)


if __name__ == "__main__":
    unittest.main()
