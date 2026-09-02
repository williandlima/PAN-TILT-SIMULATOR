"""Ponto de entrada do simulador PTU-D300E.

    python3 -m pantiltsim.main --gui
    python3 -m pantiltsim.main --headless --port /dev/ttyUSB0 --baud 9600 --rs485
    python3 -m pantiltsim.main --list-ports
    python3 -m pantiltsim.main --gui --config meu_ptu.json
"""

from __future__ import annotations

import argparse
import logging
import sys

from . import __version__
from .config import build_device_from_path
from .transport_serial import SerialTransport

log = logging.getLogger(__name__)


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _list_ports() -> int:
    ports = SerialTransport.list_ports()
    if not ports:
        print("Nenhuma porta serial encontrada.")
        return 0
    for device, description in ports:
        print(f"{device}\t{description}")
    return 0


def _run_gui(device) -> int:
    from PyQt5.QtWidgets import QApplication

    from .gui.main_window import MainWindow

    app = QApplication(sys.argv)
    window = MainWindow(device=device)
    window.show()
    return app.exec_()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Simulador do Pan-Tilt PTU-D300E (RS-485/USB) para Linux/BeagleBone e Windows."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--gui", action="store_true", help="abre a interface gráfica PyQt5 [padrão]")
    mode.add_argument("--headless", action="store_true", help="roda sem interface gráfica")
    mode.add_argument("--list-ports", action="store_true", help="lista as portas seriais e sai")

    parser.add_argument("--port", help="porta serial (obrigatório em --headless)")
    parser.add_argument("--baud", type=int, default=9600, help="baud rate (padrão: 9600)")
    parser.add_argument("--rs485", action="store_true", help="modo RS-485 half-duplex (RTS)")
    parser.add_argument("--config", help="arquivo JSON com os parâmetros do modelo simulado")
    parser.add_argument("--update-hz", type=float, default=50.0, help="taxa do motor de simulação (padrão: 50)")
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="nível de log (padrão: info)",
    )
    parser.add_argument("--version", action="version", version=f"pantiltsim {__version__}")
    return parser


def main(argv=None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.log_level)

    if args.list_ports:
        return _list_ports()

    try:
        device = build_device_from_path(args.config, update_hz=args.update_hz)
    except (OSError, ValueError) as exc:
        parser.error(f"configuração inválida: {exc}")

    if args.headless:
        from .app_cli import run_headless

        if not args.port:
            parser.error("--headless requer --port")
        return run_headless(device, args.port, args.baud, args.rs485)

    return _run_gui(device)


if __name__ == "__main__":
    sys.exit(main())
