"""Modo headless (sem interface gráfica), para BeagleBone/Linux sem monitor.

Sobe o dispositivo simulado, abre a porta serial (RS-485 ou USB) e serve
o protocolo DPCL, registrando cada comando recebido e a posição atual.
"""

from __future__ import annotations

import logging
import signal
import time

from .device import PanTiltDevice
from .protocol import DPCLProtocol
from .transport_serial import SerialServer, SerialTransport, SerialTransportConfig

log = logging.getLogger(__name__)


def run_headless(
    device: PanTiltDevice,
    port: str,
    baud: int,
    rs485: bool,
    status_interval: float = 2.0,
    auto_reconnect: bool = True,
) -> int:
    protocol = DPCLProtocol(device, on_command=lambda token, response: log.info("%s -> %s", token, response.strip()))
    transport = SerialTransport(SerialTransportConfig(port=port, baudrate=baud, rs485_mode=rs485))
    server = SerialServer(transport, protocol, auto_reconnect=auto_reconnect)

    device.start()
    try:
        server.start()
    except Exception as exc:
        log.error("Não foi possível abrir a porta serial '%s': %s", port, exc)
        device.stop()
        return 1

    log.info(
        "Simulador %s ativo em %s (%s, %d bps). Ctrl+C para sair.",
        device.model_name,
        port,
        "RS-485" if rs485 else "USB/RS-232",
        baud,
    )

    stop_requested = False

    def _handle_signal(signum, frame):
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        while not stop_requested and server.is_running:
            snap = device.snapshot()
            log.info(
                "pan=%7.2f° (%d) tilt=%7.2f° (%d) %s",
                snap["pan_deg"],
                snap["pan_counts"],
                snap["tilt_deg"],
                snap["tilt_counts"],
                "movendo" if snap["in_motion"] else "parado",
            )
            time.sleep(status_interval)
    finally:
        server.stop()
        device.stop()
        log.info("Simulador encerrado")
    return 0
