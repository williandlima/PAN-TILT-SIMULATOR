"""Janela principal da GUI do simulador PTU-D300E.

Tudo o que a interface faz é traduzido para comandos ASCII do protocolo
do fabricante e passa pelo mesmo interpretador usado pela porta serial —
ou seja, mover pela GUI exercita exatamente o mesmo caminho de código que
um controlador externo exercitaria por RS-485/USB, e o terminal embutido
permite digitar comandos DPCL crus.
"""

from __future__ import annotations

import logging
import time

from PyQt5.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QAction,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..device import PanTiltDevice
from ..protocol import DPCLProtocol
from ..tracking import GeoPoint, LinearTrajectory
from ..transport_serial import SerialServer, SerialTransport, SerialTransportConfig
from .help_dialog import HelpDialog, terminal_help_text
from .pantilt_widget import PanTiltWidget

log = logging.getLogger(__name__)

_STEP_MODE_ITEMS = [
    ("Full step", "F"),
    ("Half step", "H"),
    ("Quarter step", "Q"),
    ("Eighth step", "E"),
    ("Auto", "A"),
]
_LIMIT_MODE_ITEMS = [
    ("Fábrica (LE)", "LE"),
    ("Usuário (LU)", "LU"),
    ("Desabilitado (LD)", "LD"),
]
_CONTROL_MODE_ITEMS = [
    ("Posição (CI)", "CI"),
    ("Velocidade (CV)", "CV"),
]
_HOLD_POWER_ITEMS = [("Off", "O"), ("Low", "L"), ("Regulated", "R")]
_MOVE_POWER_ITEMS = [("Low", "L"), ("Regulated", "R"), ("High", "H")]


class _LogBridge(QObject):
    """Leva mensagens da thread serial para a thread da GUI com segurança."""

    message = pyqtSignal(str)


class MainWindow(QMainWindow):
    def __init__(self, device: PanTiltDevice | None = None):
        super().__init__()
        self.device = device or PanTiltDevice()
        self.setWindowTitle(f"Simulador {self.device.model_name} — Pan-Tilt via RS-485/USB")
        self.resize(1180, 720)

        self._log_bridge = _LogBridge()
        self._log_bridge.message.connect(self._append_log)
        self.protocol = DPCLProtocol(self.device, on_command=self._on_command)
        self.server: SerialServer | None = None
        self._updating_widgets = False

        self._demo_trajectory: LinearTrajectory | None = None
        self._demo_start_time: float = 0.0
        self._demo_timer = QTimer(self)
        self._demo_timer.setInterval(500)
        self._demo_timer.timeout.connect(self._demo_tick)

        self._build_ui()
        self._build_menu()
        self._refresh_ports()
        self.device.start()

        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(40)
        self.poll_timer.timeout.connect(self._poll_device)
        self.poll_timer.start()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        self.pantilt_widget = PanTiltWidget(self)
        root.addWidget(self.pantilt_widget, stretch=3)

        side = QVBoxLayout()
        side.addWidget(self._build_connection_group())
        side.addWidget(self._build_telemetry_group())

        tabs = QTabWidget()
        tabs.addTab(self._build_control_tab(), "Controle")
        tabs.addTab(self._build_config_tab(), "Configuração")
        tabs.addTab(self._build_tracking_tab(), "Rastreamento GPS")
        tabs.addTab(self._build_terminal_tab(), "Terminal DPCL")
        side.addWidget(tabs, stretch=1)

        container = QWidget()
        container.setLayout(side)
        container.setMinimumWidth(430)
        root.addWidget(container, stretch=2)

    # -- menus e ajuda ---------------------------------------------------
    def _build_menu(self) -> None:
        bar = self.menuBar()

        arquivo = bar.addMenu("&Arquivo")
        sair = QAction("Sair", self)
        sair.setShortcut(QKeySequence.Quit)
        sair.triggered.connect(self.close)
        arquivo.addAction(sair)

        ajuda = bar.addMenu("A&juda")
        topicos = [
            ("Primeiros passos", "Primeiros passos", QKeySequence("F1")),
            ("O núcleo do projeto", "O núcleo do projeto", None),
            ("A interface", "A interface", None),
            ("Modos de teste", "Modos de teste", QKeySequence("F2")),
            ("Rastreamento de antena por GPS", "Rastreamento de antena por GPS", QKeySequence("F4")),
            ("Comandos DPCL", "Comandos DPCL", QKeySequence("F3")),
        ]
        for rotulo, topico, atalho in topicos:
            action = QAction(rotulo, self)
            if atalho is not None:
                action.setShortcut(atalho)
            action.triggered.connect(lambda _, t=topico: self._show_help(t))
            ajuda.addAction(action)

        ajuda.addSeparator()
        sobre = QAction("Sobre o simulador", self)
        sobre.triggered.connect(self._show_about)
        ajuda.addAction(sobre)

        self.statusBar().showMessage(
            "F1 ajuda · F2 modos de teste · F3 comandos DPCL · F4 rastreamento GPS · "
            "digite ? no terminal DPCL"
        )

    def _show_help(self, topic: str = "Primeiros passos") -> None:
        dialog = HelpDialog(self.device, parent=self, topic=HelpDialog.topic_index(topic))
        dialog.exec_()

    def _show_about(self) -> None:
        snap = self.device.snapshot()
        QMessageBox.about(
            self,
            "Sobre o simulador",
            f"<b>Simulador {snap['model']}</b><br>"
            f"pantiltsim {__version__}<br><br>"
            "Simulador de pan-tilt que fala o protocolo ASCII do fabricante "
            "(DPCL) por RS-485 ou USB.<br><br>"
            f"Resolução atual: {snap['pan_resolution_arcsec']:.4f} ″/contagem (pan)<br>"
            f"Curso pan: {snap['pan_range_deg'][0]:.1f}° a {snap['pan_range_deg'][1]:.1f}°<br>"
            f"Curso tilt: {snap['tilt_range_deg'][0]:.1f}° a {snap['tilt_range_deg'][1]:.1f}°",
        )

    # -- conexão ---------------------------------------------------------
    def _build_connection_group(self) -> QGroupBox:
        box = QGroupBox("Conexão (RS-485 / USB)")
        layout = QFormLayout(box)

        self.port_combo = QComboBox()
        refresh_btn = QPushButton("Atualizar")
        refresh_btn.clicked.connect(self._refresh_ports)
        port_row = QHBoxLayout()
        port_row.addWidget(self.port_combo, stretch=1)
        port_row.addWidget(refresh_btn)
        layout.addRow("Porta:", port_row)

        options = QHBoxLayout()
        self.interface_combo = QComboBox()
        self.interface_combo.addItems(["USB / RS-232", "RS-485 half-duplex"])
        self.baud_spin = QSpinBox()
        self.baud_spin.setRange(1200, 921600)
        self.baud_spin.setValue(9600)
        options.addWidget(self.interface_combo, stretch=1)
        options.addWidget(self.baud_spin)
        layout.addRow("Interface:", options)

        self.reconnect_check = QCheckBox("Reconectar automaticamente")
        self.reconnect_check.setChecked(True)
        layout.addRow(self.reconnect_check)

        self.connect_btn = QPushButton("Conectar")
        self.connect_btn.clicked.connect(self._toggle_connection)
        layout.addRow(self.connect_btn)

        self.conn_status_label = QLabel("Desconectado — simulador ativo em modo local")
        self.conn_status_label.setWordWrap(True)
        layout.addRow(self.conn_status_label)
        return box

    # -- telemetria -------------------------------------------------------
    def _build_telemetry_group(self) -> QGroupBox:
        box = QGroupBox("Telemetria do PTU")
        grid = QGridLayout(box)
        self.telemetry_labels: dict[str, QLabel] = {}
        rows = [
            ("Pan", "pan"),
            ("Tilt", "tilt"),
            ("Resolução", "resolution"),
            ("Curso", "range"),
            ("Velocidade", "speed"),
            ("Modos", "modes"),
        ]
        for row, (title, key) in enumerate(rows):
            grid.addWidget(QLabel(f"{title}:"), row, 0)
            label = QLabel("—")
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.telemetry_labels[key] = label
            grid.addWidget(label, row, 1)
        grid.setColumnStretch(1, 1)
        return box

    # -- aba de controle ---------------------------------------------------
    def _build_control_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        form = QFormLayout()
        self.pan_target_spin = self._make_angle_spin()
        self.tilt_target_spin = self._make_angle_spin()
        form.addRow("Pan alvo:", self.pan_target_spin)
        form.addRow("Tilt alvo:", self.tilt_target_spin)

        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.1, 200.0)
        self.speed_spin.setValue(20.0)
        self.speed_spin.setSuffix(" °/s")
        form.addRow("Velocidade:", self.speed_spin)

        self.step_spin = QDoubleSpinBox()
        self.step_spin.setRange(0.1, 90.0)
        self.step_spin.setValue(5.0)
        self.step_spin.setSuffix(" °")
        form.addRow("Passo do jog:", self.step_spin)
        layout.addLayout(form)

        go_btn = QPushButton("Ir para posição  (PS/TS + PP/TP)")
        go_btn.clicked.connect(self._send_goto)
        layout.addWidget(go_btn)

        jog = QGridLayout()
        for text, (dp, dt), pos in [
            ("Tilt ▲", (0, 1), (0, 1)),
            ("Pan ◄", (-1, 0), (1, 0)),
            ("Centro", (0, 0), (1, 1)),
            ("Pan ►", (1, 0), (1, 2)),
            ("Tilt ▼", (0, -1), (2, 1)),
        ]:
            btn = QPushButton(text)
            if text == "Centro":
                btn.clicked.connect(self._send_center)
            else:
                btn.clicked.connect(lambda _, p=dp, t=dt: self._jog(p, t))
            jog.addWidget(btn, *pos)
        layout.addLayout(jog)

        actions = QGridLayout()
        buttons = [
            ("Halt (H)", "H"),
            ("Halt pan (HP)", "HP"),
            ("Halt tilt (HT)", "HT"),
            ("Reset (RE)", "RE"),
            ("Aguardar (A)", "A"),
            ("Versão (V)", "V"),
        ]
        for index, (text, command) in enumerate(buttons):
            btn = QPushButton(text)
            btn.clicked.connect(lambda _, c=command: self._send_local(c))
            actions.addWidget(btn, index // 3, index % 3)
        layout.addLayout(actions)

        self.monitor_check = QCheckBox("Modo monitor / auto-scan (ME / MD)")
        self.monitor_check.toggled.connect(
            lambda checked: self._send_local("ME" if checked else "MD")
        )
        layout.addWidget(self.monitor_check)

        layout.addStretch(1)
        return page

    def _make_angle_spin(self) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(-360.0, 360.0)
        spin.setDecimals(2)
        spin.setSuffix(" °")
        return spin

    # -- aba de configuração ------------------------------------------------
    def _build_config_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)

        self.control_mode_combo = self._make_combo(_CONTROL_MODE_ITEMS)
        self.control_mode_combo.currentIndexChanged.connect(
            lambda: self._send_combo(self.control_mode_combo)
        )
        form.addRow("Modo de controle:", self.control_mode_combo)

        self.limit_mode_combo = self._make_combo(_LIMIT_MODE_ITEMS)
        self.limit_mode_combo.currentIndexChanged.connect(
            lambda: self._send_combo(self.limit_mode_combo)
        )
        form.addRow("Limites de curso:", self.limit_mode_combo)

        self.step_mode_combo = self._make_combo(_STEP_MODE_ITEMS)
        self.step_mode_combo.setCurrentIndex(3)
        self.step_mode_combo.currentIndexChanged.connect(self._send_step_mode)
        form.addRow("Micropasso (WP/WT):", self.step_mode_combo)

        self.hold_power_combo = self._make_combo(_HOLD_POWER_ITEMS)
        self.hold_power_combo.setCurrentIndex(1)
        self.hold_power_combo.currentIndexChanged.connect(
            lambda: self._send_axis_pair("H", self.hold_power_combo)
        )
        form.addRow("Potência parado (PH/TH):", self.hold_power_combo)

        self.move_power_combo = self._make_combo(_MOVE_POWER_ITEMS)
        self.move_power_combo.setCurrentIndex(1)
        self.move_power_combo.currentIndexChanged.connect(
            lambda: self._send_axis_pair("M", self.move_power_combo)
        )
        form.addRow("Potência movendo (PM/TM):", self.move_power_combo)

        self.echo_check = QCheckBox("Eco de comandos (EE / ED)")
        self.echo_check.setChecked(True)
        self.echo_check.toggled.connect(lambda c: self._send_local("EE" if c else "ED"))
        form.addRow(self.echo_check)

        self.verbose_check = QCheckBox("Feedback verboso (FV / FT)")
        self.verbose_check.setChecked(True)
        self.verbose_check.toggled.connect(lambda c: self._send_local("FV" if c else "FT"))
        form.addRow(self.verbose_check)

        self.slaved_check = QCheckBox("Execução slaved (S / I) — move junto no 'A'")
        self.slaved_check.toggled.connect(lambda c: self._send_local("S" if c else "I"))
        form.addRow(self.slaved_check)

        defaults = QHBoxLayout()
        for text, command in [("Salvar (DS)", "DS"), ("Restaurar (DR)", "DR"), ("Fábrica (DF)", "DF")]:
            btn = QPushButton(text)
            btn.clicked.connect(lambda _, c=command: self._send_local(c))
            defaults.addWidget(btn)
        form.addRow("Configurações:", defaults)
        return page

    def _make_combo(self, items: list[tuple[str, str]]) -> QComboBox:
        combo = QComboBox()
        for label, value in items:
            combo.addItem(label, userData=value)
        return combo

    # -- aba de rastreamento GPS (antenna tracking) --------------------------
    def _build_tracking_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        intro = QLabel(
            "Rastreamento de antena por telemetria: aponta o pan-tilt automaticamente "
            "para um alvo (aeronave, drone, balão, foguete de sondagem) a partir da "
            "posição GPS da estação de solo e do alvo — o mesmo método usado por "
            "estações terrenas de satélite e antenas de telemetria reais (geodesia "
            "WGS84 completa: geodésico → ECEF → ENU, não uma aproximação de Terra plana). "
            "Comandos DPCL: <code>GO</code> (estação), <code>GX</code> (alvo), "
            "<code>GE</code>/<code>GD</code> (habilita/desabilita), <code>GA</code> "
            "(consulta ângulos) — extensão própria deste simulador, ver Ajuda → Comandos DPCL."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        observer_box = QGroupBox("Estação de solo (observador)")
        observer_form = QFormLayout(observer_box)
        self.observer_lat_spin = self._make_geo_spin(-90.0, 90.0)
        self.observer_lon_spin = self._make_geo_spin(-180.0, 180.0)
        self.observer_alt_spin = self._make_alt_spin()
        observer_form.addRow("Latitude:", self.observer_lat_spin)
        observer_form.addRow("Longitude:", self.observer_lon_spin)
        observer_form.addRow("Altitude:", self.observer_alt_spin)
        set_observer_btn = QPushButton("Definir estação (GO)")
        set_observer_btn.clicked.connect(self._send_set_observer)
        observer_form.addRow(set_observer_btn)
        layout.addWidget(observer_box)

        target_box = QGroupBox("Alvo (veículo rastreado por GPS)")
        target_form = QFormLayout(target_box)
        self.target_lat_spin = self._make_geo_spin(-90.0, 90.0)
        self.target_lon_spin = self._make_geo_spin(-180.0, 180.0)
        self.target_alt_spin = self._make_alt_spin()
        target_form.addRow("Latitude:", self.target_lat_spin)
        target_form.addRow("Longitude:", self.target_lon_spin)
        target_form.addRow("Altitude:", self.target_alt_spin)
        set_target_btn = QPushButton("Definir alvo (GX)")
        set_target_btn.clicked.connect(self._send_set_target)
        target_form.addRow(set_target_btn)
        layout.addWidget(target_box)

        demo_box = QGroupBox("Trajetória de demonstração (simula o feed de GPS do veículo)")
        demo_form = QFormLayout(demo_box)
        self.demo_heading_spin = QDoubleSpinBox()
        self.demo_heading_spin.setRange(0.0, 359.99)
        self.demo_heading_spin.setSuffix(" °")
        self.demo_heading_spin.setValue(90.0)
        demo_form.addRow("Rumo:", self.demo_heading_spin)

        self.demo_speed_spin = QDoubleSpinBox()
        self.demo_speed_spin.setRange(0.0, 1000.0)
        self.demo_speed_spin.setSuffix(" m/s")
        self.demo_speed_spin.setValue(80.0)
        demo_form.addRow("Velocidade:", self.demo_speed_spin)

        self.demo_climb_spin = QDoubleSpinBox()
        self.demo_climb_spin.setRange(-100.0, 100.0)
        self.demo_climb_spin.setSuffix(" m/s")
        self.demo_climb_spin.setValue(0.0)
        demo_form.addRow("Subida:", self.demo_climb_spin)

        self.demo_btn = QPushButton("Iniciar demonstração")
        self.demo_btn.clicked.connect(self._toggle_demo_trajectory)
        demo_form.addRow(self.demo_btn)
        layout.addWidget(demo_box)

        self.geo_enable_check = QCheckBox("Habilitar rastreamento automático (GE / GD)")
        self.geo_enable_check.toggled.connect(self._toggle_geo_tracking)
        layout.addWidget(self.geo_enable_check)

        geo_status_box = QGroupBox("Apontamento calculado")
        geo_grid = QGridLayout(geo_status_box)
        self.geo_labels: dict[str, QLabel] = {}
        for row, (title, key) in enumerate(
            [("Azimute", "az"), ("Elevação", "el"), ("Distância", "range")]
        ):
            geo_grid.addWidget(QLabel(f"{title}:"), row, 0)
            label = QLabel("—")
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.geo_labels[key] = label
            geo_grid.addWidget(label, row, 1)
        geo_grid.setColumnStretch(1, 1)
        layout.addWidget(geo_status_box)

        layout.addStretch(1)
        return page

    def _make_geo_spin(self, lo: float, hi: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(lo, hi)
        spin.setDecimals(6)
        spin.setSuffix(" °")
        return spin

    def _make_alt_spin(self) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(-500.0, 50_000.0)
        spin.setDecimals(1)
        spin.setSuffix(" m")
        return spin

    # -- aba de terminal ------------------------------------------------------
    def _build_terminal_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        hint = QLabel(
            "Digite comandos ASCII do fabricante (ex.: <code>PP1000</code>, <code>TS500</code>, "
            "<code>PR</code>). Vários comandos podem ir na mesma linha.<br>"
            "Digite <b>?</b> para o resumo dos comandos, ou <b>??</b> para a ajuda completa."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        row = QHBoxLayout()
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("PP1000 TP-500   (ou ? para ajuda)")
        self.command_input.returnPressed.connect(self._send_typed_command)
        send_btn = QPushButton("Enviar")
        send_btn.clicked.connect(self._send_typed_command)
        help_btn = QPushButton("?")
        help_btn.setMaximumWidth(34)
        help_btn.setToolTip("Resumo dos comandos DPCL")
        help_btn.clicked.connect(self._print_terminal_help)
        row.addWidget(self.command_input, stretch=1)
        row.addWidget(send_btn)
        row.addWidget(help_btn)
        layout.addLayout(row)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(4000)
        layout.addWidget(self.log_view, stretch=1)

        clear_btn = QPushButton("Limpar log")
        clear_btn.clicked.connect(self.log_view.clear)
        layout.addWidget(clear_btn)
        return page

    # ------------------------------------------------------------------
    def _refresh_ports(self) -> None:
        previous = self.port_combo.currentData()
        self.port_combo.clear()
        ports = SerialTransport.list_ports()
        for device, description in ports:
            self.port_combo.addItem(f"{device} — {description}", userData=device)
        if not ports:
            self.port_combo.addItem("(nenhuma porta encontrada)", userData=None)
        if previous:
            index = self.port_combo.findData(previous)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)

    def _toggle_connection(self) -> None:
        if self.server is not None and self.server.is_running:
            self.server.stop()
            self.server = None
            self.conn_status_label.setText("Desconectado — simulador ativo em modo local")
            self.connect_btn.setText("Conectar")
            return

        port = self.port_combo.currentData()
        if not port:
            QMessageBox.warning(self, "Conexão", "Selecione uma porta serial válida.")
            return

        rs485 = self.interface_combo.currentIndex() == 1
        transport = SerialTransport(
            SerialTransportConfig(port=port, baudrate=self.baud_spin.value(), rs485_mode=rs485)
        )
        server = SerialServer(
            transport,
            self.protocol,
            on_error=lambda exc: self._log_bridge.message.emit(f"[porta serial] {exc}"),
            auto_reconnect=self.reconnect_check.isChecked(),
        )
        try:
            server.start()
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao conectar", str(exc))
            return

        self.server = server
        mode_name = "RS-485" if rs485 else "USB/RS-232"
        self.conn_status_label.setText(f"Conectado: {port} · {mode_name} · {self.baud_spin.value()} bps")
        self.connect_btn.setText("Desconectar")

    # ------------------------------------------------------------------
    def _send_local(self, command: str) -> None:
        """Executa um comando DPCL pelo mesmo caminho usado pela porta serial."""
        self.protocol.execute_line(command)

    def _send_combo(self, combo: QComboBox) -> None:
        if not self._updating_widgets:
            self._send_local(combo.currentData())

    def _send_step_mode(self) -> None:
        if self._updating_widgets:
            return
        letter = self.step_mode_combo.currentData()
        self._send_local(f"WP{letter} WT{letter}")

    def _send_axis_pair(self, code: str, combo: QComboBox) -> None:
        if self._updating_widgets:
            return
        letter = combo.currentData()
        self._send_local(f"P{code}{letter} T{code}{letter}")

    def _send_goto(self) -> None:
        pan_counts = self.device.pan.deg_to_counts(self.pan_target_spin.value())
        tilt_counts = self.device.tilt.deg_to_counts(self.tilt_target_spin.value())
        pan_speed = self.device.pan.deg_to_counts(self.speed_spin.value())
        tilt_speed = self.device.tilt.deg_to_counts(self.speed_spin.value())
        self._send_local(f"PS{pan_speed} TS{tilt_speed} PP{pan_counts} TP{tilt_counts}")

    def _send_center(self) -> None:
        self.pan_target_spin.setValue(0.0)
        self.tilt_target_spin.setValue(0.0)
        self._send_goto()

    def _jog(self, pan_dir: int, tilt_dir: int) -> None:
        step = self.step_spin.value()
        if pan_dir:
            current = self.device.pan.counts_to_deg(self.device.pan.target_position)
            self.pan_target_spin.setValue(current + pan_dir * step)
        if tilt_dir:
            current = self.device.tilt.counts_to_deg(self.device.tilt.target_position)
            self.tilt_target_spin.setValue(current + tilt_dir * step)
        self._send_goto()

    # -- rastreamento GPS -------------------------------------------------
    def _send_set_observer(self) -> None:
        lat = self.observer_lat_spin.value()
        lon = self.observer_lon_spin.value()
        alt = self.observer_alt_spin.value()
        self._send_local(f"GO{lat},{lon},{alt}")

    def _send_set_target(self) -> None:
        lat = self.target_lat_spin.value()
        lon = self.target_lon_spin.value()
        alt = self.target_alt_spin.value()
        self._send_local(f"GX{lat},{lon},{alt}")

    def _toggle_geo_tracking(self, checked: bool) -> None:
        if self._updating_widgets:
            return
        self._send_local("GE" if checked else "GD")

    def _toggle_demo_trajectory(self) -> None:
        if self._demo_trajectory is None:
            start = GeoPoint(
                lat_deg=self.target_lat_spin.value(),
                lon_deg=self.target_lon_spin.value(),
                alt_m=self.target_alt_spin.value(),
            )
            self._demo_trajectory = LinearTrajectory(
                start=start,
                heading_deg=self.demo_heading_spin.value(),
                speed_mps=self.demo_speed_spin.value(),
                climb_mps=self.demo_climb_spin.value(),
            )
            self._demo_start_time = time.monotonic()
            self._demo_timer.start()
            self.demo_btn.setText("Parar demonstração")
        else:
            self._demo_timer.stop()
            self._demo_trajectory = None
            self.demo_btn.setText("Iniciar demonstração")

    def _demo_tick(self) -> None:
        if self._demo_trajectory is None:
            return
        elapsed = time.monotonic() - self._demo_start_time
        point = self._demo_trajectory.position_at(elapsed)

        self._updating_widgets = True
        try:
            self.target_lat_spin.setValue(point.lat_deg)
            self.target_lon_spin.setValue(point.lon_deg)
            self.target_alt_spin.setValue(point.alt_m)
        finally:
            self._updating_widgets = False

        self._send_local(f"GX{point.lat_deg},{point.lon_deg},{point.alt_m}")

    def _send_typed_command(self) -> None:
        text = self.command_input.text().strip()
        if not text:
            return
        self.command_input.clear()

        # '?' e '??' são atalhos da interface, não comandos do equipamento:
        # tratados aqui para não irem parar no protocolo como erro.
        if text == "?":
            self._print_terminal_help()
            return
        if text == "??":
            self._show_help("Comandos DPCL")
            return

        self._send_local(text)

    def _print_terminal_help(self) -> None:
        self._append_log(terminal_help_text(self.device))

    # ------------------------------------------------------------------
    def _on_command(self, token: str, response: str) -> None:
        self._log_bridge.message.emit(f">> {token}\n{response.rstrip()}")

    def _append_log(self, text: str) -> None:
        self.log_view.appendPlainText(text)

    # ------------------------------------------------------------------
    def _poll_device(self) -> None:
        snap = self.device.snapshot()
        self.pantilt_widget.set_state(snap)

        labels = self.telemetry_labels
        labels["pan"].setText(f"{snap['pan_deg']:.2f}°  ({snap['pan_counts']} contagens)")
        labels["tilt"].setText(f"{snap['tilt_deg']:.2f}°  ({snap['tilt_counts']} contagens)")
        labels["resolution"].setText(
            f"pan {snap['pan_resolution_arcsec']:.4f}\"/cont · tilt {snap['tilt_resolution_arcsec']:.4f}\"/cont"
        )
        pan_lo, pan_hi = snap["pan_range_deg"]
        tilt_lo, tilt_hi = snap["tilt_range_deg"]
        labels["range"].setText(f"pan {pan_lo:.1f}…{pan_hi:.1f}° · tilt {tilt_lo:.1f}…{tilt_hi:.1f}°")
        labels["speed"].setText(
            f"pan {snap['pan_speed_deg']:.2f}°/s · tilt {snap['tilt_speed_deg']:.2f}°/s"
            + ("  [movendo]" if snap["in_motion"] else "")
        )
        labels["modes"].setText(
            f"{snap['control_mode']} · limites {snap['limit_mode']} · {snap['step_mode']}"
            + (" · monitor" if snap["monitor"] else "")
            + (" · slaved" if snap["slaved"] else "")
        )

        look = snap.get("geo_look")
        if look is not None:
            self.geo_labels["az"].setText(f"{look.azimuth_deg:.2f}°")
            self.geo_labels["el"].setText(f"{look.elevation_deg:.2f}°")
            self.geo_labels["range"].setText(f"{look.range_m:,.1f} m")
        else:
            self.geo_labels["az"].setText("—")
            self.geo_labels["el"].setText("—")
            self.geo_labels["range"].setText("—")

        self._sync_widgets(snap)

    def _sync_widgets(self, snap: dict) -> None:
        """Reflete na GUI mudanças de estado vindas da porta serial."""
        self._updating_widgets = True
        try:
            if self.monitor_check.isChecked() != snap["monitor"]:
                self.monitor_check.setChecked(snap["monitor"])
            if self.echo_check.isChecked() != snap["echo"]:
                self.echo_check.setChecked(snap["echo"])
            if self.verbose_check.isChecked() != snap["verbose"]:
                self.verbose_check.setChecked(snap["verbose"])
            if self.slaved_check.isChecked() != snap["slaved"]:
                self.slaved_check.setChecked(snap["slaved"])
            if self.geo_enable_check.isChecked() != snap["geo_tracking"]:
                self.geo_enable_check.setChecked(snap["geo_tracking"])
            self._sync_combo(self.control_mode_combo, "CV" if snap["control_mode"] == "velocity" else "CI")
            self._sync_combo(
                self.limit_mode_combo,
                {"factory": "LE", "user": "LU", "disabled": "LD"}[snap["limit_mode"]],
            )
            self._sync_combo(
                self.step_mode_combo,
                {"full": "F", "half": "H", "quarter": "Q", "eighth": "E", "auto": "A"}[snap["step_mode"]],
            )
            self._sync_combo(self.hold_power_combo, snap["hold_power"][0].upper())
            self._sync_combo(self.move_power_combo, snap["move_power"][0].upper())
        finally:
            self._updating_widgets = False

    def _sync_combo(self, combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0 and combo.currentIndex() != index:
            combo.setCurrentIndex(index)

    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802
        self._demo_timer.stop()
        if self.server is not None:
            self.server.stop()
        self.device.stop()
        super().closeEvent(event)
