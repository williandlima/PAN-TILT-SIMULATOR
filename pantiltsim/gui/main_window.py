"""Janela principal da GUI do simulador PTU-D300E."""

from __future__ import annotations

from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..device import ControlMode, PanTiltDevice
from ..protocol import DPCLProtocol
from ..transport_serial import SerialServer, SerialTransport, SerialTransportConfig
from .pantilt_widget import PanTiltWidget


class _LogBridge(QObject):
    message = pyqtSignal(str)


class MainWindow(QMainWindow):
    def __init__(self, device: PanTiltDevice | None = None):
        super().__init__()
        self.setWindowTitle("Simulador PTU-D300E — Pan-Tilt via RS-485/USB")
        self.resize(980, 620)

        self.device = device or PanTiltDevice()
        self._log_bridge = _LogBridge()
        self._log_bridge.message.connect(self._append_log)
        self.protocol = DPCLProtocol(self.device, on_command=self._on_command)
        self.server: SerialServer | None = None

        self._build_ui()
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
        side.addWidget(self._build_status_group())
        side.addWidget(self._build_manual_group())
        side.addWidget(self._build_log_group(), stretch=1)
        root.addLayout(side, stretch=2)

    def _build_connection_group(self) -> QGroupBox:
        box = QGroupBox("Conexão (RS-485 / USB)")
        layout = QFormLayout(box)

        self.port_combo = QComboBox()
        refresh_btn = QPushButton("Atualizar")
        refresh_btn.clicked.connect(self._refresh_ports)
        port_row = QHBoxLayout()
        port_row.addWidget(self.port_combo, stretch=1)
        port_row.addWidget(refresh_btn)
        layout.addRow("Porta serial:", port_row)

        self.interface_combo = QComboBox()
        self.interface_combo.addItems(["USB (porta serial virtual)", "RS-485 (half-duplex)"])
        layout.addRow("Interface:", self.interface_combo)

        self.baud_spin = QSpinBox()
        self.baud_spin.setRange(1200, 921600)
        self.baud_spin.setValue(9600)
        layout.addRow("Baud rate:", self.baud_spin)

        self.connect_btn = QPushButton("Conectar")
        self.connect_btn.clicked.connect(self._toggle_connection)
        layout.addRow(self.connect_btn)

        self.conn_status_label = QLabel("Desconectado (modo local)")
        layout.addRow("Estado:", self.conn_status_label)
        return box

    def _build_status_group(self) -> QGroupBox:
        box = QGroupBox("Status do PTU")
        layout = QFormLayout(box)
        self.pan_status_label = QLabel("0.00°")
        self.tilt_status_label = QLabel("0.00°")
        self.motion_status_label = QLabel("PARADO")
        self.mode_status_label = QLabel("POSIÇÃO")
        layout.addRow("Pan atual:", self.pan_status_label)
        layout.addRow("Tilt atual:", self.tilt_status_label)
        layout.addRow("Movimento:", self.motion_status_label)
        layout.addRow("Modo de controle:", self.mode_status_label)
        return box

    def _build_manual_group(self) -> QGroupBox:
        box = QGroupBox("Controle manual (envia comandos DPCL)")
        layout = QVBoxLayout(box)

        form = QFormLayout()
        self.pan_target_spin = QDoubleSpinBox()
        self.pan_target_spin.setRange(-360.0, 360.0)
        self.pan_target_spin.setDecimals(2)
        self.pan_target_spin.setSuffix(" °")
        form.addRow("Pan alvo:", self.pan_target_spin)

        self.tilt_target_spin = QDoubleSpinBox()
        self.tilt_target_spin.setRange(-360.0, 360.0)
        self.tilt_target_spin.setDecimals(2)
        self.tilt_target_spin.setSuffix(" °")
        form.addRow("Tilt alvo:", self.tilt_target_spin)

        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(1, 6000)
        self.speed_spin.setValue(self.device.pan.desired_speed)
        self.speed_spin.setSuffix(" contagens/s")
        form.addRow("Velocidade (PS/TS):", self.speed_spin)

        self.step_spin = QDoubleSpinBox()
        self.step_spin.setRange(0.1, 90.0)
        self.step_spin.setValue(5.0)
        self.step_spin.setSuffix(" °")
        form.addRow("Passo do jog:", self.step_spin)

        layout.addLayout(form)

        go_btn = QPushButton("Ir para posição (PP/TP)")
        go_btn.clicked.connect(self._send_goto)
        layout.addWidget(go_btn)

        jog_grid = QGridLayout()
        up_btn = QPushButton("Tilt ▲")
        down_btn = QPushButton("Tilt ▼")
        left_btn = QPushButton("Pan ◄")
        right_btn = QPushButton("Pan ►")
        up_btn.clicked.connect(lambda: self._jog(0, 1))
        down_btn.clicked.connect(lambda: self._jog(0, -1))
        left_btn.clicked.connect(lambda: self._jog(-1, 0))
        right_btn.clicked.connect(lambda: self._jog(1, 0))
        jog_grid.addWidget(up_btn, 0, 1)
        jog_grid.addWidget(left_btn, 1, 0)
        jog_grid.addWidget(right_btn, 1, 2)
        jog_grid.addWidget(down_btn, 2, 1)
        layout.addLayout(jog_grid)

        btn_row = QHBoxLayout()
        halt_btn = QPushButton("Halt (H)")
        halt_btn.clicked.connect(lambda: self._send_local("H "))
        reset_btn = QPushButton("Reset (R)")
        reset_btn.clicked.connect(lambda: self._send_local("R "))
        btn_row.addWidget(halt_btn)
        btn_row.addWidget(reset_btn)
        layout.addLayout(btn_row)

        opts_row = QHBoxLayout()
        self.limits_checkbox = QCheckBox("Limites de curso ativos")
        self.limits_checkbox.setChecked(True)
        self.limits_checkbox.toggled.connect(self._toggle_limits)
        self.velocity_mode_checkbox = QCheckBox("Modo velocidade contínua (CV)")
        self.velocity_mode_checkbox.toggled.connect(self._toggle_velocity_mode)
        opts_row.addWidget(self.limits_checkbox)
        opts_row.addWidget(self.velocity_mode_checkbox)
        layout.addLayout(opts_row)

        return box

    def _build_log_group(self) -> QGroupBox:
        box = QGroupBox("Log do protocolo (comandos/respostas)")
        layout = QVBoxLayout(box)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        layout.addWidget(self.log_view)
        return box

    # ------------------------------------------------------------------
    def _refresh_ports(self) -> None:
        current = self.port_combo.currentText()
        self.port_combo.clear()
        ports = SerialTransport.list_ports()
        for device, description in ports:
            self.port_combo.addItem(f"{device} — {description}", userData=device)
        if not ports:
            self.port_combo.addItem("(nenhuma porta encontrada)", userData=None)
        idx = self.port_combo.findText(current)
        if idx >= 0:
            self.port_combo.setCurrentIndex(idx)

    def _toggle_connection(self) -> None:
        if self.server is not None and self.server.is_running:
            self.server.stop()
            self.server = None
            self.conn_status_label.setText("Desconectado (modo local)")
            self.connect_btn.setText("Conectar")
            return

        port = self.port_combo.currentData()
        if not port:
            QMessageBox.warning(self, "Conexão", "Selecione uma porta serial válida.")
            return

        rs485 = self.interface_combo.currentIndex() == 1
        config = SerialTransportConfig(
            port=port,
            baudrate=self.baud_spin.value(),
            rs485_mode=rs485,
        )
        transport = SerialTransport(config)
        self.server = SerialServer(transport, self.protocol, on_error=self._on_transport_error)
        try:
            self.server.start()
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao conectar", str(exc))
            self.server = None
            return

        mode_name = "RS-485" if rs485 else "USB"
        self.conn_status_label.setText(f"Conectado em {port} ({mode_name}, {self.baud_spin.value()} bps)")
        self.connect_btn.setText("Desconectar")

    def _on_transport_error(self, exc: Exception) -> None:
        self._log_bridge.message.emit(f"[ERRO DE PORTA] {exc}\n")
        self.conn_status_label.setText("Erro na conexão — verifique a porta")
        self.connect_btn.setText("Conectar")
        self.server = None

    # ------------------------------------------------------------------
    def _send_local(self, ascii_command: str) -> None:
        self.protocol.feed(ascii_command.encode("ascii"))

    def _send_goto(self) -> None:
        pan_counts = self.device.pan.config.deg_to_counts(self.pan_target_spin.value())
        tilt_counts = self.device.tilt.config.deg_to_counts(self.tilt_target_spin.value())
        speed = self.speed_spin.value()
        self._send_local(f"PS{speed} ")
        self._send_local(f"TS{speed} ")
        self._send_local(f"PP{pan_counts} ")
        self._send_local(f"TP{tilt_counts} ")

    def _jog(self, pan_dir: int, tilt_dir: int) -> None:
        step = self.step_spin.value()
        if pan_dir:
            new_pan = self.device.pan.config.counts_to_deg(self.device.pan.target_position) + pan_dir * step
            self.pan_target_spin.setValue(new_pan)
        if tilt_dir:
            new_tilt = self.device.tilt.config.counts_to_deg(self.device.tilt.target_position) + tilt_dir * step
            self.tilt_target_spin.setValue(new_tilt)
        self._send_goto()

    def _toggle_limits(self, checked: bool) -> None:
        self._send_local("LE " if checked else "LD ")

    def _toggle_velocity_mode(self, checked: bool) -> None:
        self._send_local("CV " if checked else "CI ")

    # ------------------------------------------------------------------
    def _on_command(self, token: str, response: str) -> None:
        self._log_bridge.message.emit(f">> {token}\n{response}")

    def _append_log(self, text: str) -> None:
        self.log_view.appendPlainText(text.rstrip("\n"))

    # ------------------------------------------------------------------
    def _poll_device(self) -> None:
        snap = self.device.snapshot()
        self.pantilt_widget.set_state(
            pan_deg=snap["pan_deg"],
            tilt_deg=snap["tilt_deg"],
            pan_target=snap["pan_target_deg"],
            tilt_target=snap["tilt_target_deg"],
            in_motion=snap["in_motion"],
        )
        self.pan_status_label.setText(f"{snap['pan_deg']:.2f}°")
        self.tilt_status_label.setText(f"{snap['tilt_deg']:.2f}°")
        self.motion_status_label.setText("EM MOVIMENTO" if snap["in_motion"] else "PARADO")
        self.mode_status_label.setText(
            "VELOCIDADE" if self.device.control_mode == ControlMode.VELOCITY else "POSIÇÃO"
        )

    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802
        if self.server is not None:
            self.server.stop()
        self.device.stop()
        super().closeEvent(event)
