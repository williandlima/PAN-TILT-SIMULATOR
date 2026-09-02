#!/usr/bin/env python3
"""Cliente de exemplo: fala DPCL com o simulador (ou com um PTU real).

Serve para duas coisas: validar o simulador de fora para dentro, e servir
de referência de como um controlador seu deve conversar com o
PTU-D300E — o mesmo código funciona com o equipamento real, bastando
apontar para a porta dele.

    # terminal interativo
    python3 tools/ptu_client.py --port /dev/pts/5

    # sequência de demonstração (consulta resolução, move, aguarda, lê)
    python3 tools/ptu_client.py --port /dev/pts/5 --demo

    # um comando só
    python3 tools/ptu_client.py --port COM4 --command "PP2000"
"""

from __future__ import annotations

import argparse
import sys
import time

import serial


class PTUClient:
    """Controlador mínimo para o protocolo ASCII do PTU."""

    def __init__(self, port: str, baudrate: int = 9600, rs485: bool = False, timeout: float = 2.0):
        self.serial = serial.Serial(port, baudrate=baudrate, timeout=timeout)
        if rs485:
            try:
                from serial.rs485 import RS485Settings

                self.serial.rs485_mode = RS485Settings(rts_level_for_tx=True, rts_level_for_rx=False)
            except Exception as exc:  # o adaptador pode fazer isso em hardware
                print(f"[aviso] modo RS-485 por software indisponível: {exc}", file=sys.stderr)

    def send(self, command: str, timeout: float = 5.0) -> str:
        """Envia um comando e espera a resposta terminar.

        A resposta do PTU termina na primeira linha iniciada por ``*``
        (sucesso) ou ``!`` (erro); antes dela pode vir o eco do comando,
        se o eco estiver ligado. Esperar por essa linha — em vez de
        dormir um tempo fixo — é o que mantém o enlace sincronizado
        mesmo em comandos demorados como o ``A`` (await), que só
        responde quando o movimento termina.
        """
        self.serial.reset_input_buffer()
        self.serial.write(f"{command} ".encode("ascii"))
        self.serial.flush()

        lines: list[str] = []
        pending = b""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            chunk = self.serial.read(1)
            if not chunk:
                continue
            pending += chunk
            if not pending.endswith(b"\n"):
                continue
            line = pending.decode("ascii", errors="ignore").strip()
            pending = b""
            if line:
                lines.append(line)
            if line.startswith(("*", "!")):
                return "\n".join(lines)
        raise TimeoutError(f"sem resposta para '{command}' em {timeout}s")

    def query_number(self, command: str) -> float:
        """Lê uma resposta numérica em modo terso (``* <valor>``)."""
        response = self.send(command)
        last = response.splitlines()[-1] if response else ""
        if not last.startswith("*"):
            raise RuntimeError(f"resposta inesperada para '{command}': {response!r}")
        return float(last[1:].strip())

    def close(self) -> None:
        self.serial.close()


def run_demo(client: PTUClient) -> int:
    print("Preparando o enlace (eco desligado, feedback terso)...")
    client.send("ED")
    client.send("FT")

    pan_res = client.query_number("PR")
    tilt_res = client.query_number("TR")
    print(f"Resolução: pan {pan_res}\"/contagem · tilt {tilt_res}\"/contagem")

    counts_per_deg_pan = 3600.0 / pan_res
    counts_per_deg_tilt = 3600.0 / tilt_res
    print(f"Curso pan: {client.query_number('PN'):.0f} .. {client.query_number('PX'):.0f} contagens")

    speed = int(40 * counts_per_deg_pan)
    print(f"Ajustando velocidade para {speed} contagens/s ...")
    client.send(f"PS{speed}")
    client.send(f"TS{int(40 * counts_per_deg_tilt)}")

    for pan_deg, tilt_deg in [(45.0, 20.0), (-60.0, -15.0), (0.0, 0.0)]:
        pan_counts = int(pan_deg * counts_per_deg_pan)
        tilt_counts = int(tilt_deg * counts_per_deg_tilt)
        print(f"Movendo para pan={pan_deg}° tilt={tilt_deg}° ...", end=" ", flush=True)
        started = time.monotonic()
        client.send(f"PP{pan_counts}")
        client.send(f"TP{tilt_counts}")
        client.send("A", timeout=60.0)  # o await só responde quando o movimento acaba
        reached_pan = client.query_number("PP") / counts_per_deg_pan
        reached_tilt = client.query_number("TP") / counts_per_deg_tilt
        print(f"chegou em {reached_pan:.2f}° / {reached_tilt:.2f}° em {time.monotonic() - started:.1f}s")

    return 0


def run_interactive(client: PTUClient) -> int:
    print("Terminal DPCL. Digite comandos (ex.: PP1000, PR, PP). 'sair' encerra.")
    while True:
        try:
            line = input("ptu> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if line.lower() in {"sair", "quit", "exit"}:
            return 0
        if line:
            print(client.send(line))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Cliente de exemplo para o PTU-D300E / simulador")
    parser.add_argument("--port", required=True, help="porta serial do simulador ou do PTU")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--rs485", action="store_true", help="usa modo RS-485 half-duplex")
    parser.add_argument("--demo", action="store_true", help="roda uma sequência de demonstração")
    parser.add_argument("--command", help="envia um único comando e sai")
    args = parser.parse_args(argv)

    client = PTUClient(args.port, args.baud, args.rs485)
    try:
        if args.command:
            print(client.send(args.command))
            return 0
        if args.demo:
            return run_demo(client)
        return run_interactive(client)
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
