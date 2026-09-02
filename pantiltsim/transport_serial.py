"""Camada de transporte serial (RS-485 e USB).

Do ponto de vista de software, RS-485 e USB aparecem como uma porta
serial (COM no Windows; /dev/ttyUSB*, /dev/ttyACM*, /dev/ttyO* ou
/dev/ttyS* em Linux/BeagleBone):

    - **RS-485**: via conversor USB-RS485 ou UART RS-485 nativa (comum na
      BeagleBone, com controle de direção por RTS). O pyserial trata o
      half-duplex com ``serial.rs485.RS485Settings`` quando o driver do
      adaptador suporta.
    - **USB**: o PTU-D300E expõe uma porta serial virtual quando ligado
      por USB, então o mesmo protocolo ASCII roda sem alteração — muda
      apenas o nome da porta.

Por isso uma única classe atende os dois casos; escolher RS-485 apenas
habilita o modo half-duplex do pyserial.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

import serial
from serial.tools import list_ports

try:
    from serial.rs485 import RS485Settings
except ImportError:  # pragma: no cover
    RS485Settings = None

log = logging.getLogger(__name__)


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
    """Porta serial (RS-485 ou USB) por onde trafega o protocolo DPCL."""

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
        if cfg.rs485_mode:
            if RS485Settings is None:
                log.warning("pyserial sem suporte a RS485Settings; seguindo em modo full-duplex")
            else:
                try:
                    ser.rs485_mode = RS485Settings(rts_level_for_tx=True, rts_level_for_rx=False)
                except (NotImplementedError, ValueError, OSError) as exc:
                    # Vários drivers/adaptadores fazem o toggle de direção em
                    # hardware e rejeitam a configuração por software.
                    log.warning("Adaptador não aceita modo RS-485 por software (%s); seguindo assim mesmo", exc)
        self._serial = ser
        log.info("Porta %s aberta a %d bps (%s)", cfg.port, cfg.baudrate, "RS-485" if cfg.rs485_mode else "USB/RS-232")

    def close(self) -> None:
        if self._serial is not None and self._serial.is_open:
            self._serial.close()
            log.info("Porta %s fechada", self.config.port)
        self._serial = None

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def read_available(self) -> bytes:
        if self._serial is None:
            raise SerialTransportError("Porta serial não está aberta")
        waiting = self._serial.in_waiting
        if waiting:
            return self._serial.read(waiting)
        return self._serial.read(1)  # bloqueia até `timeout`

    def write(self, data: bytes) -> None:
        if self._serial is None:
            raise SerialTransportError("Porta serial não está aberta")
        self._serial.write(data)
        self._serial.flush()

    @staticmethod
    def list_ports() -> list[tuple[str, str]]:
        return [(p.device, p.description) for p in list_ports.comports()]


class SerialTransportError(Exception):
    pass


class SerialServer:
    """Liga um `SerialTransport` a um `DPCLProtocol`, em thread própria.

    Com ``auto_reconnect``, uma desconexão física (cabo removido, dongle
    USB reenumerado) não derruba o simulador: o laço tenta reabrir a
    porta periodicamente até conseguir.
    """

    def __init__(self, transport: SerialTransport, protocol, on_error=None, auto_reconnect: bool = False):
        self.transport = transport
        self.protocol = protocol
        self.on_error = on_error
        self.auto_reconnect = auto_reconnect
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
            self._thread.join(timeout=2.0)
            self._thread = None
        self.transport.close()

    @property
    def is_running(self) -> bool:
        return self._running

    def _run_loop(self) -> None:
        while self._running:
            try:
                data = self.transport.read_available()
                if not data:
                    continue
                response = self.protocol.feed(data)
                if response:
                    self.transport.write(response)
            except Exception as exc:
                log.error("Erro na porta serial: %s", exc)
                if self.on_error is not None:
                    self.on_error(exc)
                if not self.auto_reconnect:
                    self._running = False
                    return
                self._reconnect()

    def _reconnect(self) -> None:
        self.transport.close()
        while self._running:
            time.sleep(1.0)
            try:
                self.transport.open()
                log.info("Porta serial reconectada")
                return
            except Exception as exc:
                log.debug("Reconexão falhou: %s", exc)
