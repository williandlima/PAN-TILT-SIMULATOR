"""Ponto de entrada do simulador PTU-D300E.

Uso:
    python -m pantiltsim.main --gui
    python -m pantiltsim.main --headless --port /dev/ttyUSB0 --baud 9600
    python -m pantiltsim.main --list-ports
"""

from __future__ import annotations

import argparse
import sys

from .transport_serial import SerialTransport


def _list_ports() -> int:
    ports = SerialTransport.list_ports()
    if not ports:
        print("Nenhuma porta serial encontrada.")
        return 0
    for device, description in ports:
        print(f"{device}\t{description}")
    return 0


def _run_gui() -> int:
    from PyQt5.QtWidgets import QApplication

    from .gui.main_window import MainWindow

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec_()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Simulador do Pan-Tilt PTU-D300E (RS-485/USB), compatível Linux/BeagleBone e Windows."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--gui", action="store_true", help="Abre a interface gráfica (PyQt5) [padrão]")
    mode.add_argument("--headless", action="store_true", help="Roda sem interface gráfica (console)")
    mode.add_argument("--list-ports", action="store_true", help="Lista as portas seriais disponíveis e sai")

    parser.add_argument("--port", help="Porta serial (obrigatório em --headless)")
    parser.add_argument("--baud", type=int, default=9600, help="Baud rate (padrão: 9600)")
    parser.add_argument("--rs485", action="store_true", help="Usa modo RS-485 (half-duplex via RTS)")
    return parser


def main(argv=None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.list_ports:
        return _list_ports()

    if args.headless:
        from .app_cli import run_headless

        if not args.port:
            parser.error("--headless requer --port")
        return run_headless(args.port, args.baud, args.rs485)

    return _run_gui()


if __name__ == "__main__":
    sys.exit(main())
