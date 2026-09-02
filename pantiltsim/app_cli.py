"""Modo headless (sem interface gráfica), útil para BeagleBone/Linux sem monitor.

Sobe o dispositivo simulado, abre a porta serial (RS-485 ou USB) informada
e fica servindo o protocolo DPCL, imprimindo no terminal cada comando
recebido e a posição atual periodicamente.
"""

from __future__ import annotations

import argparse
import signal
import sys
import time

from .device import PanTiltDevice
from .protocol import DPCLProtocol
from .transport_serial import SerialServer, SerialTransport, SerialTransportConfig


def _log_command(token: str, response: str) -> None:
    print(f">> {token}\n{response}", end="")


def run_headless(port: str, baud: int, rs485: bool, status_interval: float = 2.0) -> int:
    device = PanTiltDevice()
    protocol = DPCLProtocol(device, on_command=_log_command)

    config = SerialTransportConfig(port=port, baudrate=baud, rs485_mode=rs485)
    transport = SerialTransport(config)

    errors: list[Exception] = []
    server = SerialServer(transport, protocol, on_error=errors.append)

    device.start()
    try:
        server.start()
    except Exception as exc:
        print(f"Erro ao abrir a porta serial '{port}': {exc}", file=sys.stderr)
        device.stop()
        return 1

    mode_name = "RS-485" if rs485 else "USB"
    print(f"Simulador PTU-D300E ativo em {port} ({mode_name}, {baud} bps). Ctrl+C para sair.")

    stop_requested = False

    def _handle_sigint(signum, frame):
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, _handle_sigint)

    try:
        while not stop_requested and server.is_running:
            snap = device.snapshot()
            print(
                f"[status] pan={snap['pan_deg']:7.2f}° tilt={snap['tilt_deg']:7.2f}° "
                f"movimento={'sim' if snap['in_motion'] else 'nao'}"
            )
            time.sleep(status_interval)
    finally:
        server.stop()
        device.stop()

    if errors:
        print(f"Encerrado por erro de porta: {errors[0]}", file=sys.stderr)
        return 1
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Simulador PTU-D300E (modo headless)")
    parser.add_argument("--port", required=True, help="Porta serial (ex.: COM3, /dev/ttyUSB0, /dev/ttyO4)")
    parser.add_argument("--baud", type=int, default=9600, help="Baud rate (padrão: 9600)")
    parser.add_argument("--rs485", action="store_true", help="Usa modo RS-485 (half-duplex via RTS)")
    return parser


def main(argv=None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return run_headless(args.port, args.baud, args.rs485)


if __name__ == "__main__":
    sys.exit(main())
