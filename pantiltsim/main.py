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
    try:
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QApplication

        from .gui.main_window import MainWindow
    except ImportError:
        print(
            "A interface gráfica precisa do PyQt5, que não está instalado.\n"
            "  Instale com:  pip install \"pantiltsim[gui]\"   (ou: pip install PyQt5)\n"
            "  Sem monitor?  use o modo headless:  ptu-sim --headless --port <porta>",
            file=sys.stderr,
        )
        return 2

    # Precisa vir ANTES de criar o QApplication. Sem isso, em monitores com
    # escala de tela (comum no Windows), o layout às vezes calcula o tamanho
    # certo mas alguns widgets não são repintados até a janela ser mexida —
    # um glitch de redesenho, não uma falha real de dados.
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    window = MainWindow(device=device)
    window.show()
    return app.exec_()


_EPILOGO = """
modos de teste:
  local        Abra a interface e comande por ela; nenhuma porta é necessária.
                 ptu-sim --gui
  loopback     Duas portas virtuais: o simulador em uma ponta, seu software na
               outra. Linux: socat; Windows: com0com.
                 socat -d -d pty,raw,echo=0,link=/tmp/ptu-sim \\
                            pty,raw,echo=0,link=/tmp/ptu-cliente
                 ptu-sim --headless --port /tmp/ptu-sim
                 python3 tools/ptu_client.py --port /tmp/ptu-cliente --demo
  fiação real  Um conversor de cada lado do barramento (9600 8N1 por padrão).
                 ptu-sim --headless --port /dev/ttyUSB0 --rs485
  autoteste    Aceitação ponta a ponta, sem hardware (Linux/macOS).
                 python3 tools/autoteste.py
  suíte        pip install -e ".[dev]" && pytest
               Linux: 82 passam. Windows: 75 passam e 7 são pulados (usam PTY).

o núcleo, em uma frase:
  O protocolo do fabricante trabalha em CONTAGENS, não em graus. Pergunte a
  resolução com PR/TR e calcule contagens_por_grau = 3600 / resolução; nunca
  fixe a conversão no código, porque ela muda com o micropasso e o modelo.

ajuda dentro do programa:
  Na interface: menu Ajuda, ou F1 (primeiros passos), F2 (modos de teste),
  F3 (comandos DPCL) e F4 (Geo Pointing Module / rastreamento GPS). No
  terminal DPCL, digite ? para o resumo dos comandos.

documentação:
  docs/GUIA_DO_OPERADOR.md  guia para quem só opera a interface (sem jargão)
  docs/PROCEDIMENTO.md      instalação, teste e utilização, passo a passo
  docs/PROTOCOL.md          protocolo completo e o que foi confirmado em hardware
"""


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Simulador do Pan-Tilt PTU-D300E (RS-485/USB) para Linux/BeagleBone e Windows.",
        epilog=_EPILOGO,
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
