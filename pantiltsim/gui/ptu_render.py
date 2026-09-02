"""Renderizador 3D leve do PTU-D300E com antena helicoidal.

Desenha a unidade como ela é fisicamente: uma base fixa (que abriga o
acionamento de pan), um prato giratório, um garfo (yoke) de dois braços
verticais, o eixo de tilt entre os braços e a placa de payload onde a
antena helicoidal está acoplada.

Assim o pan (rotação em torno do eixo vertical) e o tilt (rotação em
torno do eixo horizontal entre os braços) aparecem geometricamente
corretos, e não como uma "dica" 2D: o modelo é montado em coordenadas
3D, transformado pelas rotações de pan/tilt e projetado com uma câmera
ortográfica fixa, com faces ordenadas por profundidade (algoritmo do
pintor) e sombreamento lambertiano.

Não depende de nenhuma imagem externa nem de biblioteca 3D: apenas
QPainter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from PyQt5.QtCore import QPointF
from PyQt5.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF

Vec3 = tuple[float, float, float]

# Câmera: azimute e elevação fixos, projeção ortográfica.
# Azimute escolhido para que, em pan=0, a antena (boresight em +Y) apareça
# de perfil e não apontada para longe do observador.
CAMERA_AZIMUTH_DEG = 65.0
CAMERA_ELEVATION_DEG = 17.0
LIGHT_DIR: Vec3 = (-0.35, -0.55, 0.76)

# Extensão de referência do modelo, usada para manter a escala estável
# enquanto a unidade gira (sem "respiração" de zoom a cada quadro).
MODEL_REFERENCE_EXTENT = 470.0
MODEL_CENTER_Z = 150.0

# Paleta: alumínio claro (acabamento típico das unidades da série D),
# com detalhes escuros e antena em tom de cobre.
COLOR_FLANGE = QColor(96, 102, 112)
COLOR_BASE = QColor(176, 182, 190)
COLOR_BASE_DARK = QColor(120, 126, 136)
COLOR_TURNTABLE = QColor(150, 156, 166)
COLOR_YOKE = QColor(196, 201, 208)
COLOR_PLATE = QColor(88, 94, 104)
COLOR_CONNECTOR = QColor(48, 52, 60)
COLOR_GROUND_PLANE = QColor(168, 172, 180)
COLOR_HELIX = QColor(214, 152, 78)
COLOR_MAST = QColor(120, 126, 136)


@dataclass
class Drawable:
    """Uma face (polígono preenchido) ou um segmento de linha, com profundidade."""

    points: list[Vec3]
    color: QColor
    depth: float = 0.0
    filled: bool = True
    width: float = 1.0
    shade: bool = True


@dataclass
class Scene:
    items: list[Drawable] = field(default_factory=list)

    def add(self, item: Drawable) -> None:
        self.items.append(item)


# ----------------------------------------------------------------------
# Álgebra 3D
# ----------------------------------------------------------------------
def rot_z(p: Vec3, angle_rad: float) -> Vec3:
    """Rotação de pan. Ângulo positivo gira no sentido horário visto de cima."""
    x, y, z = p
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    return (x * c + y * s, -x * s + y * c, z)


def rot_x_about(p: Vec3, angle_rad: float, pivot_z: float) -> Vec3:
    """Rotação de tilt em torno do eixo X, na altura do eixo de tilt.

    Ângulo positivo levanta o boresight (que aponta para +Y).
    """
    x, y, z = p
    z -= pivot_z
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    return (x, y * c - z * s, y * s + z * c + pivot_z)


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _normalize(v: Vec3) -> Vec3:
    length = math.sqrt(sum(c * c for c in v))
    if length < 1e-9:
        return (0.0, 0.0, 1.0)
    return (v[0] / length, v[1] / length, v[2] / length)


def project(p: Vec3, az_rad: float, el_rad: float) -> tuple[float, float, float]:
    """Projeta um ponto 3D. Devolve (x_tela, y_tela, profundidade)."""
    x, y, z = p
    ca, sa = math.cos(az_rad), math.sin(az_rad)
    xc = x * ca - y * sa
    yc = x * sa + y * ca
    ce, se = math.cos(el_rad), math.sin(el_rad)
    depth = yc * ce + z * se
    zs = -yc * se + z * ce
    return (xc, -zs, depth)


# ----------------------------------------------------------------------
# Primitivas geométricas
# ----------------------------------------------------------------------
def _lerp(a: Vec3, b: Vec3, t: float) -> Vec3:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def _subdivide_quad(quad: list[Vec3], n: int) -> list[list[Vec3]]:
    """Divide um quadrilátero em n x n sub-quads.

    O algoritmo do pintor ordena por profundidade média: faces grandes
    perto de objetos pequenos (a hélice da antena) acabam ordenadas
    errado. Subdividir aproxima a média da profundidade local e elimina
    a maior parte dos artefatos, sem precisar de z-buffer.
    """
    if n <= 1:
        return [quad]
    p0, p1, p2, p3 = quad

    def point(u: float, v: float) -> Vec3:
        return _lerp(_lerp(p0, p1, u), _lerp(p3, p2, u), v)

    quads = []
    for i in range(n):
        for j in range(n):
            u0, u1 = i / n, (i + 1) / n
            v0, v1 = j / n, (j + 1) / n
            quads.append([point(u0, v0), point(u1, v0), point(u1, v1), point(u0, v1)])
    return quads


def box(center: Vec3, size: Vec3, color: QColor, subdivide: int = 1) -> list[Drawable]:
    """Caixa alinhada aos eixos, como seis faces quadrangulares."""
    cx, cy, cz = center
    hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
    x0, x1 = cx - hx, cx + hx
    y0, y1 = cy - hy, cy + hy
    z0, z1 = cz - hz, cz + hz

    corners = {
        "000": (x0, y0, z0), "100": (x1, y0, z0), "110": (x1, y1, z0), "010": (x0, y1, z0),
        "001": (x0, y0, z1), "101": (x1, y0, z1), "111": (x1, y1, z1), "011": (x0, y1, z1),
    }
    quads = [
        ("001", "101", "111", "011"),  # topo
        ("000", "010", "110", "100"),  # base
        ("000", "100", "101", "001"),  # frente (-Y)
        ("110", "010", "011", "111"),  # trás (+Y)
        ("100", "110", "111", "101"),  # direita (+X)
        ("010", "000", "001", "011"),  # esquerda (-X)
    ]
    faces: list[Drawable] = []
    for quad in quads:
        points = [corners[k] for k in quad]
        for piece in _subdivide_quad(points, subdivide):
            faces.append(Drawable(points=piece, color=color))
    return faces


def cylinder(
    center: Vec3,
    radius: float,
    length: float,
    color: QColor,
    axis: str = "z",
    segments: int = 24,
) -> list[Drawable]:
    """Cilindro com eixo em 'x', 'y' ou 'z', como uma tira de quads mais as tampas."""
    faces: list[Drawable] = []
    cx, cy, cz = center
    half = length / 2

    def point(angle: float, offset: float) -> Vec3:
        ca, sa = math.cos(angle), math.sin(angle)
        if axis == "z":
            return (cx + radius * ca, cy + radius * sa, cz + offset)
        if axis == "x":
            return (cx + offset, cy + radius * ca, cz + radius * sa)
        return (cx + radius * ca, cy + offset, cz + radius * sa)

    step = 2 * math.pi / segments
    for i in range(segments):
        a0, a1 = i * step, (i + 1) * step
        faces.append(
            Drawable(
                points=[point(a0, -half), point(a1, -half), point(a1, half), point(a0, half)],
                color=color,
            )
        )

    for offset in (-half, half):
        cap = [point(i * step, offset) for i in range(segments)]
        faces.append(Drawable(points=cap, color=color))
    return faces


def helix(
    start: Vec3,
    length: float,
    radius: float,
    turns: float,
    color: QColor,
    axis: str = "y",
    samples_per_turn: int = 22,
    width: float = 3.0,
) -> list[Drawable]:
    """Hélice 3D (a antena helicoidal), como segmentos de linha ordenáveis."""
    sx, sy, sz = start
    total = max(2, int(turns * samples_per_turn))
    points: list[Vec3] = []
    for i in range(total + 1):
        t = i / total
        angle = t * turns * 2 * math.pi
        ca, sa = math.cos(angle), math.sin(angle)
        if axis == "y":
            points.append((sx + radius * ca, sy + t * length, sz + radius * sa))
        else:
            points.append((sx + radius * ca, sy + radius * sa, sz + t * length))

    return [
        Drawable(points=[points[i], points[i + 1]], color=color, filled=False, width=width, shade=False)
        for i in range(len(points) - 1)
    ]


# ----------------------------------------------------------------------
# Modelo do PTU-D300E
# ----------------------------------------------------------------------
TILT_AXIS_Z = 196.0
ANTENNA_AXIS_Z = TILT_AXIS_Z + 62.0


def build_scene(pan_deg: float, tilt_deg: float) -> Scene:
    """Monta a cena completa já com as rotações de pan e tilt aplicadas."""
    scene = Scene()
    pan_rad = math.radians(pan_deg)
    tilt_rad = math.radians(tilt_deg)

    # --- Partes fixas (não giram) -------------------------------------
    static: list[Drawable] = []
    static += box((0, 0, 6), (152, 152, 12), COLOR_FLANGE, subdivide=2)   # flange de fixação
    static += box((0, 0, 48), (120, 118, 72), COLOR_BASE, subdivide=2)    # carcaça do acionamento de pan
    static += box((0, 0, 88), (128, 126, 8), COLOR_BASE_DARK)             # aba superior da carcaça
    static += box((0, -66, 40), (44, 16, 30), COLOR_CONNECTOR)        # painel de conectores
    scene.items.extend(static)

    # --- Partes que giram com o pan ------------------------------------
    rotating: list[Drawable] = []
    rotating += cylinder((0, 0, 99), 50, 14, COLOR_TURNTABLE)         # prato giratório
    rotating += box((0, 0, 113), (140, 100, 14), COLOR_YOKE, subdivide=3)  # base do garfo
    for side in (-1, 1):                                              # braços do garfo
        # Braços são placas verticais relativamente estreitas que terminam
        # logo acima do eixo de tilt, como na unidade real: assim o payload
        # fica visível em vez de encoberto pelo garfo.
        rotating += box((side * 58, 0, 166), (22, 60, 92), COLOR_YOKE, subdivide=3)
        # cubo do eixo de tilt na face interna de cada braço (eixo ao longo de X)
        rotating += cylinder((side * 42, 0, TILT_AXIS_Z), 15, 12, COLOR_PLATE, axis="x")

    # --- Partes que giram com pan e tilt (payload) ----------------------
    payload: list[Drawable] = []
    payload += box((0, 0, TILT_AXIS_Z + 11), (88, 100, 14), COLOR_PLATE, subdivide=4)  # placa de payload
    payload += box((0, -26, TILT_AXIS_Z + 38), (16, 16, 40), COLOR_MAST, subdivide=2)  # poste de sustentação
    payload += cylinder((0, -16, ANTENNA_AXIS_Z), 34, 6, COLOR_GROUND_PLANE, axis="y")  # plano de terra
    payload += cylinder((0, 26, ANTENNA_AXIS_Z), 3.0, 84, COLOR_MAST, axis="y")         # mastro central
    payload += helix(
        start=(0, -10, ANTENNA_AXIS_Z),
        length=96,
        radius=21,
        turns=7.0,
        color=COLOR_HELIX,
        axis="y",
        width=3.0,
    )

    for item in payload:
        item.points = [rot_x_about(p, tilt_rad, TILT_AXIS_Z) for p in item.points]
    rotating.extend(payload)

    for item in rotating:
        item.points = [rot_z(p, pan_rad) for p in item.points]
    scene.items.extend(rotating)

    return scene


# ----------------------------------------------------------------------
# Desenho
# ----------------------------------------------------------------------
def _shaded(color: QColor, points: list[Vec3]) -> QColor:
    if len(points) < 3:
        return color
    normal = _normalize(_cross(_sub(points[1], points[0]), _sub(points[2], points[0])))
    lambert = sum(n * l for n, l in zip(normal, LIGHT_DIR))
    factor = 0.45 + 0.55 * max(0.0, abs(lambert))
    return QColor(
        min(255, int(color.red() * factor)),
        min(255, int(color.green() * factor)),
        min(255, int(color.blue() * factor)),
    )


def render(painter: QPainter, width: float, height: float, pan_deg: float, tilt_deg: float) -> None:
    """Desenha o PTU na posição informada, ajustado à área disponível."""
    scene = build_scene(pan_deg, tilt_deg)
    az = math.radians(CAMERA_AZIMUTH_DEG)
    el = math.radians(CAMERA_ELEVATION_DEG)

    scale = min(width, height) / MODEL_REFERENCE_EXTENT
    origin_x = width / 2
    origin_y = height * 0.52 + MODEL_CENTER_Z * scale * math.cos(el)

    def to_screen(p: Vec3) -> tuple[QPointF, float]:
        sx, sy, depth = project(p, az, el)
        return QPointF(origin_x + sx * scale, origin_y + sy * scale), depth

    _draw_ground_shadow(painter, to_screen, scale)

    projected: list[tuple[float, Drawable, list[QPointF]]] = []
    for item in scene.items:
        pts: list[QPointF] = []
        depth_sum = 0.0
        for p in item.points:
            point, depth = to_screen(p)
            pts.append(point)
            depth_sum += depth
        projected.append((depth_sum / len(item.points), item, pts))

    projected.sort(key=lambda entry: entry[0], reverse=True)

    for _, item, pts in projected:
        if item.filled:
            color = _shaded(item.color, item.points) if item.shade else item.color
            painter.setBrush(QBrush(color))
            # Contorno na própria cor: fecha as fendas de antialiasing entre
            # polígonos vizinhos sem desenhar as divisões internas das faces
            # subdivididas. A separação entre faces vem do sombreamento.
            painter.setPen(QPen(color, 0.8))
            painter.drawPolygon(QPolygonF(pts))
        else:
            painter.setPen(QPen(item.color, item.width * scale * 1.6))
            painter.drawLine(pts[0], pts[1])


def _draw_ground_shadow(painter: QPainter, to_screen, scale: float) -> None:
    center, _ = to_screen((0.0, 0.0, 0.0))
    painter.setPen(QPen(QColor(0, 0, 0, 0)))
    painter.setBrush(QBrush(QColor(0, 0, 0, 60)))
    painter.drawEllipse(center, 150 * scale, 52 * scale)
