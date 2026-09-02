"""Camada de transporte serial (RS-485 e USB).

Do ponto de vista de software, tanto RS-485 quanto USB aparecem como uma
porta serial (COM em Windows, /dev/ttyUSB*, /dev/ttyACM* ou /dev/ttyS* em
Linux/BeagleBone):

    - RS-485: normalmente através de um conversor USB-RS485 ou de uma
      UART RS-485 nativa (comum em BeagleBone, com controle de direção
      por RTS ou por um GPIO dedicado). Aqui usamos o suporte nativo do
      pyserial (`serial.rs485.RS485Settings`) para alternar
      automaticamente o sentido de transmissão via RTS quando disponível
      no driver do adaptador.
    - USB: o próprio PTU-D300E expõe uma porta serial virtual (CDC/FTDI)
      quando conectado via USB, então o mesmo código de protocolo
      ASCII funciona sem alterações — só muda o nome da porta.

Por isso uma única classe `SerialTransport` atende os dois casos; a
escolha de RS-485 apenas liga o `RS485Settings` do pyserial.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

import serial
from serial.tools import list_ports

try:
    from serial.rs485 import RS485Settings
except ImportError:  # pragma: no cover - deveria sempre existir no pyserial >=3
    RS485Settings = None


@dataclass
class SerialTransportConfig:
    port: str
    baudrate: int = 9600
    bytesize: int = serial.EIGHTBITS
    parity: str = serial.PARITY_NONE
    stopbits: float = serial.STOPBITS_ONE
    timeout: float = 0.05
    rs485_mode: bool = False


class SerialTransport:
    """Porta serial física (RS-485 ou USB) usada para falar o protocolo DPCL."""

    def __init__(self, config: SerialTransportConfig):
        self.config = config
        self._serial: serial.Serial | None = None

    def open(self) -> None:
        cfg = self.config
        ser = serial.Serial(
            port=cfg.port,
            baudrate=cfg.baudrate,
            bytesize=cfg.bytesize,
            parity=cfg.parity,
            stopbits=cfg.stopbits,
            timeout=cfg.timeout,
        )
        if cfg.rs485_mode and RS485Settings is not None:
            ser.rs485_mode = RS485Settings(rts_level_for_tx=True, rts_level_for_rx=False)
        self._serial = ser

    def close(self) -> None:
        if self._serial is not None and self._serial.is_open:
            self._serial.close()
        self._serial = None

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def read_available(self) -> bytes:
        assert self._serial is not None
        waiting = self._serial.in_waiting
        if waiting:
            return self._serial.read(waiting)
        # bloqueia até `timeout` esperando ao menos 1 byte
        return self._serial.read(1)

    def write(self, data: bytes) -> None:
        assert self._serial is not None
        self._serial.write(data)
        self._serial.flush()

    @staticmethod
    def list_ports() -> list[tuple[str, str]]:
        return [(p.device, p.description) for p in list_ports.comports()]


class SerialServer:
    """Liga um SerialTransport a um DPCLProtocol, rodando em thread própria."""

    def __init__(self, transport: SerialTransport, protocol, on_error=None):
        self.transport = transport
        self.protocol = protocol
        self.on_error = on_error
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self.transport.open()
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, name="ptu-serial", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        self.transport.close()

    @property
    def is_running(self) -> bool:
        return self._running

    def _run_loop(self) -> None:
        try:
            while self._running:
                data = self.transport.read_available()
                if not data:
                    continue
                response = self.protocol.feed(data)
                if response:
                    self.transport.write(response)
        except Exception as exc:  # porta fechada/desconectada etc.
            self._running = False
            if self.on_error is not None:
                self.on_error(exc)
