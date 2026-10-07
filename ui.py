"""Interface Pygame (renderização e input; regras em game.py)."""

from __future__ import annotations

import math
import os
from concurrent.futures import Future
from pathlib import Path

import pygame

from animal_images import AnimalImage, AnimalImageService
from game import MAX_ENERGY, GameSession, GameState
from skip_list import BuildingNode

SCREEN_W, SCREEN_H = 1280, 720
FPS = 60
BG_IMAGE_PATH = "assets/background.png"
BG_FALLBACK_COLOR = (22, 30, 56)
FLOOR_H = 40
BUILD_W = 64
SPACING = 120
X0 = 200
GROUND_Y = 640
IMAGES_DIR = Path(__file__).resolve().parent / "assets" / "imagens"
IMAGE_SIZE = (200, 200)

LEVEL_COLORS = [
    (255, 214, 102),
    (255, 159, 67),
    (255, 107, 107),
    (238, 90, 200),
    (162, 120, 255),
    (90, 160, 255),
    (72, 214, 232),
    (80, 220, 160),
    (170, 230, 90),
    (240, 240, 120),
    (255, 255, 255),
    (200, 200, 200),
]


def world_x(idx: int) -> float:
    return X0 + idx * SPACING


def star_points(cx: float, cy: float, r_out: float, r_in: float, n: int = 5) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for i in range(n * 2):
        ang = -math.pi / 2 + i * math.pi / n
        r = r_out if i % 2 == 0 else r_in
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return pts


def shade(c: tuple[int, int, int], f: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(v * f))) for v in c)


def load_animal_image(
    animal_id: int,
    animal_class: str,
    animal_name: str,
    size: tuple[int, int] = IMAGE_SIZE,
) -> pygame.Surface:
    """Carrega imagem do animal com Fallback Triplo (ZERO CRASHES garantido).

    Ordem de tentativa:
      1º  assets/imagens/{animal_id}.jpg  (foto específica)
      2º  assets/imagens/default_{class}.jpg  (foto genérica da classe)
      3º  assets/imagens/default_unknown.png  (interrogação geral)
      4º  Surface sólido com nome do animal (fallback de segurança máxima)
    """
    candidates = [
        IMAGES_DIR / f"{animal_id}.jpg",
        IMAGES_DIR / f"default_{animal_class.lower()}.jpg",
        IMAGES_DIR / "default_unknown.png",
    ]
    try:
        for path in candidates:
            if path.is_file():
                img = pygame.image.load(str(path))
                img = pygame.transform.scale(img, size)
                return img.convert_alpha()
    except Exception:
        pass  # captura FileNotFoundError, pygame.error, etc.

    # Fallback de segurança máxima: retângulo colorido + nome
    surf = pygame.Surface(size)
    surf.fill((80, 60, 100))
    pygame.draw.rect(surf, (180, 170, 200), surf.get_rect(), 3)
    try:
        font = pygame.font.SysFont("dejavusans,arial", 14)
        label = font.render(animal_name[:28], True, (255, 255, 255))
        surf.blit(
            label,
            (size[0] // 2 - label.get_width() // 2, size[1] // 2 - label.get_height() // 2),
        )
        sub = font.render(f"({animal_class})", True, (200, 200, 220))
        surf.blit(
            sub,
            (size[0] // 2 - sub.get_width() // 2, size[1] // 2 + label.get_height()),
        )
    except Exception:
        pass  # se até a fonte falhar, retorna o retângulo puro
    return surf


class PygameApp:
    def __init__(self, screen: pygame.Surface, session: GameSession) -> None:
        self.screen = screen
        self.session = session
        self.clock = pygame.time.Clock()
        self.f_s = pygame.font.SysFont("dejavusans,arial", 12)
        self.f_m = pygame.font.SysFont("dejavusans,arial", 16)
        self.f_i = pygame.font.SysFont("dejavusans,arial", 17, italic=True)
        self.f_b = pygame.font.SysFont("dejavusans,arial", 30, bold=True)
        self.digits = [
            self.f_s.render(str(i), True, (20, 20, 30)) for i in range(1, 13)
        ]
        self.label_cache: dict[int, pygame.Surface] = {}
        self.image_cache: dict[int, pygame.Surface] = {}
        self._target_image: pygame.Surface | None = None
        self._last_target_id: int | None = None
        self.image_service = AnimalImageService()
        self._image_surfaces: dict[str, pygame.Surface] = {}
        self._image_request_key: tuple[int, str | None] | None = None
        self._image_future: Future[AnimalImage] | None = None
        self._image_result: AnimalImage | None = None
        self._combat_image: pygame.Surface | None = None
        self.bg = self._load_bg()
        self.show_legend = False
        self.show_debug = False
        self.dbg = (0, 0)
        self.cam_x = 0.0
        self.p_x = world_x(0) + BUILD_W / 2
        self.p_y = self._feet_y(0)
        node = self.session.current_node
        if node is not None:
            self.p_x = world_x(node.idx) + BUILD_W / 2
        self.cam_x = self.p_x - SCREEN_W / 2
        self._prepare_target_image()

    def _load_bg(self) -> pygame.Surface | None:
        if os.path.isfile(BG_IMAGE_PATH):
            try:
                img = pygame.image.load(BG_IMAGE_PATH).convert()
                w = max(1, int(img.get_width() * SCREEN_H / img.get_height()))
                return pygame.transform.smoothscale(img, (w, SCREEN_H))
            except pygame.error:
                pass
        return None

    def _get_target_image(self) -> pygame.Surface | None:
        """Retorna a imagem do alvo atual com cache (fallback triplo)."""
        target = self.session.target
        if target is None:
            return None
        if target.id == self._last_target_id and self._target_image is not None:
            return self._target_image
        # Cache global por ID
        if target.id in self.image_cache:
            self._target_image = self.image_cache[target.id]
        else:
            self._target_image = load_animal_image(
                target.id,
                target.taxonomic_class,
                target.common_name,
            )
            # Limitar cache para não estourar memória
            if len(self.image_cache) > 200:
                self.image_cache.clear()
            self.image_cache[target.id] = self._target_image
        self._last_target_id = target.id
        return self._target_image

    def _prepare_target_image(self) -> None:
        target = self.session.target
        if target is None:
            return
        taxon_id = getattr(target, "inaturalist_id", None)
        request_key = (target.id, taxon_id)
        if request_key == self._image_request_key:
            return
        self._image_request_key = request_key
        self._image_result = None
        self._combat_image = None
        self._image_future = self.image_service.request(taxon_id)
        if taxon_id and taxon_id in self._image_surfaces:
            self._combat_image = self._image_surfaces[taxon_id]

    def _poll_target_image(self) -> None:
        self._prepare_target_image()
        future = self._image_future
        if future is None or not future.done() or self._image_result is not None:
            return
        try:
            result = future.result()
        except Exception:
            result = AnimalImage(None, None)
        self._image_result = result
        if not result.available or result.image_path is None:
            return
        try:
            image = pygame.image.load(str(result.image_path)).convert_alpha()
            width, height = image.get_size()
            max_width, max_height = 304, 304
            scale = min(max_width / max(1, width), max_height / max(1, height))
            scaled_size = (max(1, round(width * scale)), max(1, round(height * scale)))
            self._combat_image = pygame.transform.smoothscale(image, scaled_size)
            if result.taxon_id:
                if len(self._image_surfaces) >= 50:
                    self._image_surfaces.pop(next(iter(self._image_surfaces)))
                self._image_surfaces[result.taxon_id] = self._combat_image
        except (pygame.error, OSError, ValueError):
            self._combat_image = None

    def _feet_y(self, floor: int) -> float:
        return GROUND_Y - floor * FLOOR_H - 4

    def update(self, dt: float) -> None:
        self._poll_target_image()
        node = self.session.current_node
        if node is None:
            return
        k = min(1.0, dt * 9)
        self.p_x += (world_x(node.idx) + BUILD_W / 2 - self.p_x) * k
        self.p_y += (self._feet_y(self.session.current_level) - self.p_y) * k
        self.cam_x += (self.p_x - SCREEN_W / 2 - self.cam_x) * min(1.0, dt * 8)

    def draw_background(self) -> None:
        if self.bg is None:
            self.screen.fill(BG_FALLBACK_COLOR)
        else:
            bw = self.bg.get_width()
            off = -int(self.cam_x * 0.25) % bw
            x = off - bw
            while x < SCREEN_W:
                self.screen.blit(self.bg, (x, 0))
                x += bw
        pygame.draw.rect(
            self.screen, (30, 34, 44), (0, GROUND_Y, SCREEN_W, SCREEN_H - GROUND_Y)
        )
        pygame.draw.line(
            self.screen, (90, 96, 110), (0, GROUND_Y), (SCREEN_W, GROUND_Y), 3
        )

    def draw_zip(self, src: BuildingNode, lvl: int, dst: BuildingNode) -> None:
        cam = self.cam_x
        y = GROUND_Y - lvl * FLOOR_H - FLOOR_H // 2
        sx = world_x(src.idx) + BUILD_W - cam
        ex = world_x(dst.idx) - cam
        active = (
            src is self.session.current_node
            and lvl == self.session.current_level
            and self.session.state == GameState.PLAYING
        )
        col = LEVEL_COLORS[lvl % len(LEVEL_COLORS)]
        x1, x2 = max(sx, -20), min(ex, SCREEN_W + 20)
        if x2 > x1:
            pygame.draw.line(
                self.screen,
                (255, 255, 255) if active else col,
                (x1, y),
                (x2, y),
                4 if active else 2,
            )
        if -10 < sx < SCREEN_W + 10:
            pygame.draw.circle(self.screen, col, (int(sx), y), 4)
        if -10 < ex < SCREEN_W + 10:
            pygame.draw.circle(self.screen, col, (int(ex), y), 4)

    def label(self, node: BuildingNode) -> pygame.Surface:
        s = self.label_cache.get(node.idx)
        if s is None:
            if len(self.label_cache) > 600:
                self.label_cache.clear()
            s = self.f_s.render(node.name, True, (210, 214, 224))
            self.label_cache[node.idx] = s
        return s

    def draw_building(self, node: BuildingNode) -> None:
        sl = self.session.scenario
        h = sl.height_of(node)
        sx = world_x(node.idx) - self.cam_x
        top = GROUND_Y - h * FLOOR_H
        body = pygame.Rect(int(sx), top, BUILD_W, h * FLOOR_H)
        pygame.draw.rect(self.screen, shade(node.color, 0.45), body)
        is_player = node is self.session.current_node
        for f in range(h):
            fy = GROUND_Y - (f + 1) * FLOOR_H
            win = pygame.Rect(int(sx) + 4, fy + 4, BUILD_W - 8, FLOOR_H - 8)
            hot = is_player and f == self.session.current_level and self.session.state == GameState.PLAYING
            pygame.draw.rect(
                self.screen,
                (255, 245, 170) if hot else node.color,
                win,
                border_radius=3,
            )
            if f < len(self.digits):
                self.screen.blit(self.digits[f], (win.x + 4, win.y + 3))
            if not sl.has_forward(node, f) and node is not sl.head:
                if f < node.level:
                    pygame.draw.line(
                        self.screen,
                        (40, 40, 50),
                        (win.right - 10, win.y + 4),
                        (win.right - 4, win.y + 10),
                        2,
                    )
        if is_player:
            pygame.draw.rect(self.screen, (255, 255, 255), body.inflate(4, 4), 2)
        lbl = self.label(node)
        cx = sx + BUILD_W / 2
        self.screen.blit(
            self.f_s.render(f"#{node.idx}", True, (170, 176, 190)),
            (cx - 20, GROUND_Y + 6),
        )
        self.screen.blit(lbl, (cx - lbl.get_width() / 2, GROUND_Y + 20))

    def draw_player(self) -> None:
        px, py = self.p_x - self.cam_x, self.p_y
        pygame.draw.rect(
            self.screen, (235, 80, 70), (px - 6, py - 20, 12, 18), border_radius=3
        )
        pygame.draw.circle(self.screen, (250, 220, 180), (int(px), int(py - 26)), 6)

    def draw_energy_bar(self) -> None:
        x, y, w, h = 18, 108, 230, 16
        pygame.draw.rect(self.screen, (32, 36, 48), (x, y, w, h), border_radius=4)
        pygame.draw.rect(self.screen, (75, 82, 100), (x, y, w, h), 1, border_radius=4)
        max_e = max(1, self.session.max_energy)
        ratio = max(0.0, min(1.0, self.session.energy / max_e))
        fill_w = int((w - 2) * ratio)
        if fill_w > 0:
            if ratio > 0.5:
                col = (65, 205, 115)
            elif ratio > 0.25:
                col = (255, 180, 50)
            else:
                col = (240, 70, 70)
            pygame.draw.rect(self.screen, col, (x + 1, y + 1, fill_w, h - 2), border_radius=3)
        txt = self.f_s.render(
            f"Energia: {self.session.energy}/{self.session.max_energy}",
            True,
            (225, 230, 240),
        )
        self.screen.blit(txt, (x + w + 10, y))

    def draw_minimap(self) -> None:
        x0, x1, y = 40, SCREEN_W - 40, 692
        pygame.draw.rect(
            self.screen, (60, 66, 82), (x0, y, x1 - x0, 6), border_radius=3
        )
        n = max(1, self.session.scenario.size)
        mx = lambda i: x0 + (x1 - x0) * i / n
        node = self.session.current_node
        if node is not None:
            pygame.draw.circle(
                self.screen, (255, 255, 255), (int(mx(node.idx)), y + 3), 6
            )
        self.screen.blit(
            self.f_s.render(f"{self.session.scenario.size} prédios", True, (150, 156, 170)),
            (x1 - 70, y + 10),
        )

    def text(self, s: str, pos: tuple[int, int], font=None, color=(235, 238, 245)) -> None:
        self.screen.blit((font or self.f_m).render(s, True, color), pos)

    def draw_hud(self) -> None:
        panel = pygame.Surface((620, 160), pygame.SRCALPHA)
        panel.fill((10, 12, 20, 175))
        self.screen.blit(panel, (8, 8))
        self.text(
            f"Classe do alvo: {self.session.target_class_label()}",
            (18, 14),
            color=(255, 215, 0),
        )
        node = self.session.current_node
        idx = node.idx if node else 0
        vic_txt = f"Vitórias: {self.session.victories}    " if self.session.victories > 0 else ""
        self.text(
            f"{vic_txt}Movimentos: {self.session.moves}     Prédio atual: #{idx}  andar {self.session.current_level + 1}",
            (18, 38),
        )
        if node and node is not self.session.scenario.head:
            self.text(
                f"Posição: {node.name}",
                (18, 60),
                self.f_s,
                (190, 196, 210),
            )
        moves = (
            self.session.scenario.get_available_moves(node, self.session.current_level)
            if node
            else []
        )
        zip_at_floor = next((d for lvl, d in moves if lvl == self.session.current_level), None)
        if zip_at_floor:
            info = f"Tirolesa andar {self.session.current_level + 1}: → {zip_at_floor.name} (+{zip_at_floor.idx - idx} índices)"
        else:
            info = f"Andar {self.session.current_level + 1}: sem tirolesa neste nível"
        self.text(
            info, (18, 80), self.f_s, LEVEL_COLORS[self.session.current_level % len(LEVEL_COLORS)]
        )
        self.draw_energy_bar()
        if self.session.message:
            msg_col = (120, 240, 160) if "vitória" in self.session.message.lower() else (255, 140, 140)
            self.text(self.session.message, (18, 134), self.f_s, msg_col)

        help_ = [
            "↑/↓ andar   ESPAÇO/→ tirolesa",
            "R reinicia turno  N novo alvo",
            "C legenda  F1 debug",
        ]
        for i, h in enumerate(help_):
            s = self.f_s.render(h, True, (200, 205, 220))
            self.screen.blit(s, (SCREEN_W - s.get_width() - 14, 12 + i * 16))
        if self.show_legend:
            y = 70
            for bnode in self.session.scenario.buildings:
                pygame.draw.rect(self.screen, bnode.color, (SCREEN_W - 190, y, 12, 12))
                self.text(f"{bnode.name} ({bnode.animal_class[:14]})", (SCREEN_W - 172, y - 3), self.f_s)
                y += 16
        if self.show_debug:
            vb, ve = self.dbg
            root_key = self.session.tree.search_root_key()
            self.text(
                f"FPS {self.clock.get_fps():.0f} | vis {vb}/{ve} | raiz Splay id={root_key}",
                (10, SCREEN_H - 22),
                self.f_s,
                (120, 255, 160),
            )

    def draw_overlay(self) -> None:
        if self.session.state not in (GameState.GAME_OVER, GameState.TARGET_REACHED):
            return
        veil = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        veil.fill((0, 0, 0, 160))
        self.screen.blit(veil, (0, 0))
        if self.session.state == GameState.GAME_OVER:
            title = "GAME OVER"
            t = self.f_b.render(title, True, (255, 120, 120))
        else:
            title = "ALVO ALCANÇADO!"
            t = self.f_b.render(title, True, (120, 240, 150))
        self.screen.blit(t, (SCREEN_W / 2 - t.get_width() / 2, 260))
        sub = self.session.message or "Fim de jogo."
        s = self.f_m.render(sub + "   [R] reiniciar turno  [N] novo alvo", True, (235, 238, 245))
        self.screen.blit(s, (SCREEN_W / 2 - s.get_width() / 2, 310))

    def draw_wrapped_text(
        self,
        value: str,
        x: int,
        y: int,
        max_width: int,
        font: pygame.font.Font,
        color: tuple[int, int, int],
        line_gap: int = 4,
    ) -> int:
        lines: list[str] = []
        line = ""
        for word in value.split():
            candidate = f"{line} {word}".strip()
            if line and font.size(candidate)[0] > max_width:
                lines.append(line)
                line = word
            else:
                line = candidate
        if line:
            lines.append(line)
        for line in lines:
            rendered = font.render(line, True, color)
            self.screen.blit(rendered, (x, y))
            y += rendered.get_height() + line_gap
        return y

    def draw_combat_overlay(self) -> None:
        if self.session.state != GameState.COMBAT:
            return
        veil = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        veil.fill((7, 10, 16, 205))
        self.screen.blit(veil, (0, 0))

        panel = pygame.Rect(188, 48, 904, 624)
        pygame.draw.rect(self.screen, (28, 34, 43), panel, border_radius=6)
        pygame.draw.rect(self.screen, (119, 151, 137), panel, 2, border_radius=6)
        title = self.f_b.render("COMBATE", True, (241, 220, 154))
        self.screen.blit(title, (panel.centerx - title.get_width() // 2, panel.y + 20))

        image_frame = pygame.Rect(panel.x + 30, panel.y + 88, 340, 356)
        pygame.draw.rect(self.screen, (18, 23, 31), image_frame, border_radius=4)
        pygame.draw.rect(self.screen, (74, 91, 89), image_frame, 1, border_radius=4)
        if self._combat_image is not None:
            image_rect = self._combat_image.get_rect(center=image_frame.center)
            self.screen.blit(self._combat_image, image_rect)
        else:
            loading = self._image_future is not None and not self._image_future.done()
            label = "Carregando imagem..." if loading else "Imagem não disponível"
            placeholder = self.f_m.render(label, True, (189, 199, 190))
            self.screen.blit(
                placeholder,
                (image_frame.centerx - placeholder.get_width() // 2,
                 image_frame.centery - placeholder.get_height() // 2),
            )

        target = self.session.target
        right_x = panel.x + 402
        right_width = panel.right - right_x - 32
        y = panel.y + 98
        if target is not None:
            self.text("NOME POPULAR", (right_x, y), self.f_s, (161, 180, 165))
            y += 20
            y = self.draw_wrapped_text(
                target.common_name, right_x, y, right_width, self.f_b, (245, 241, 224)
            ) + 10
            self.text("NOME CIENTÍFICO", (right_x, y), self.f_s, (161, 180, 165))
            y += 19
            y = self.draw_wrapped_text(
                target.scientific_name or "—", right_x, y, right_width, self.f_i,
                (201, 211, 199),
            ) + 12
            self.text("CLASSE", (right_x, y), self.f_s, (161, 180, 165))
            y += 19
            y = self.draw_wrapped_text(
                target.taxonomic_class, right_x, y, right_width, self.f_m,
                (224, 232, 219),
            ) + 10

        result = self._image_result
        if result is not None and result.available:
            attribution = result.attribution or "Atribuição não informada"
            self.text("FOTO", (right_x, y), self.f_s, (161, 180, 165))
            y += 17
            y = self.draw_wrapped_text(
                attribution, right_x, y, right_width, self.f_s, (200, 207, 199), 2
            ) + 6
            if result.license_code:
                y = self.draw_wrapped_text(
                    f"Licença: {result.license_code}", right_x, y, right_width,
                    self.f_s, (200, 207, 199), 2,
                )
            if result.taxon_url:
                self.draw_wrapped_text(
                    result.taxon_url, right_x, min(y + 2, panel.bottom - 66),
                    right_width, self.f_s, (145, 178, 161), 2,
                )

        prompt = self.f_m.render(
            "ENTER / ESPAÇO: resolver combate (50/50)", True, (241, 220, 154)
        )
        self.screen.blit(
            prompt, (panel.centerx - prompt.get_width() // 2, panel.bottom - 48)
        )

    def draw(self) -> None:
        self.draw_background()
        lo = max(0, int((self.cam_x - X0) // SPACING) - 1)
        hi = int((self.cam_x + SCREEN_W - X0) // SPACING) + 1
        buildings, edges = self.session.scenario.scan_window(lo, hi)
        self.dbg = (len(buildings), len(edges))
        for src, lvl, dst in edges:
            self.draw_zip(src, lvl, dst)
        for b in buildings:
            self.draw_building(b)
        self.draw_player()
        self.draw_minimap()
        self.draw_hud()
        self.draw_overlay()
        self.draw_combat_overlay()
        pygame.display.flip()

    def handle_key(self, key: int) -> bool:
        if key == pygame.K_ESCAPE:
            return False
        if self.session.state == GameState.COMBAT and key in (
            pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE
        ):
            self.session.resolve_combat()
            self._prepare_target_image()
        elif key in (pygame.K_UP, pygame.K_w):
            self.session.change_floor(+1)
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.session.change_floor(-1)
        elif key in (pygame.K_SPACE, pygame.K_RIGHT, pygame.K_d, pygame.K_RETURN):
            self.session.take_zip_line()
        elif key == pygame.K_r:
            self.session.restart_turn()
        elif key == pygame.K_n:
            self.session.new_target()
            self._prepare_target_image()
        elif key == pygame.K_c:
            self.show_legend = not self.show_legend
        elif key == pygame.K_F1:
            self.show_debug = not self.show_debug
        return True

    def run(self) -> None:
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
                elif ev.type == pygame.KEYDOWN:
                    running = self.handle_key(ev.key) and running
            self.update(dt)
            self.draw()
        self.image_service.shutdown(wait=False)
        pygame.quit()
