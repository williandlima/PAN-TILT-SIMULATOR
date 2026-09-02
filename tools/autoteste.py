#!/usr/bin/env python3
"""Teste de aceitação do simulador, ponta a ponta, sem hardware nenhum.

Cria um par de portas seriais virtuais, sobe o simulador em uma ponta e,
pela outra, executa a mesma sequência que um controlador real executaria:
consulta a resolução, lê os limites, comanda movimento, aguarda a
conclusão, confere a posição alcançada, testa o halt e os limites de
curso. No fim imprime um relatório com PASSOU/FALHOU por item.

    python3 tools/autoteste.py

Use como verificação de instalação ("está tudo funcionando?") e como
roteiro do que o equipamento deve responder. Em Windows, onde não há
PTY, rode a suíte `pytest` e o teste manual com com0com descritos em
docs/PROCEDIMENTO.md.
"""

from __future__ import annotations

import os
import select
import sys
import threading
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from pantiltsim.config import build_device  # noqa: E402
from pantiltsim.protocol import DPCLProtocol  # noqa: E402
from pantiltsim.transport_serial import (  # noqa: E402
    SerialServer,
    SerialTransport,
    SerialTransportConfig,
)


class Relatorio:
    def __init__(self) -> None:
        self.itens: list[tuple[str, bool, str]] = []

    def checa(self, descricao: str, condicao: bool, detalhe: str = "") -> None:
        self.itens.append((descricao, bool(condicao), detalhe))
        marca = "PASSOU" if condicao else "FALHOU"
        print(f"  [{marca}] {descricao}" + (f"  ({detalhe})" if detalhe else ""))

    @property
    def falhas(self) -> int:
        return sum(1 for _, ok, _ in self.itens if not ok)

    def resumo(self) -> int:
        total = len(self.itens)
        print("\n" + "=" * 62)
        if self.falhas:
            print(f"RESULTADO: {total - self.falhas}/{total} itens passaram — {self.falhas} FALHA(S)")
            return 1
        print(f"RESULTADO: {total}/{total} itens passaram — simulador operacional")
        return 0


class ParSerialVirtual:
    """Par de portas seriais virtuais ligadas uma na outra, via PTYs.

    O simulador abre o lado que o sistema apresenta como porta serial
    (``/dev/pts/N``); o "controlador" usa o outro lado. Uma ponte de
    bytes liga os dois pares, de modo que ambos os lados tenham um nome
    de porta utilizável por qualquer software (inclusive um programa
    externo seu).
    """

    def __init__(self) -> None:
        self._master_sim, slave_sim = os.openpty()
        self._master_cli, slave_cli = os.openpty()
        self.porta_simulador = os.ttyname(slave_sim)
        self.porta_controlador = os.ttyname(slave_cli)
        self._slaves = (slave_sim, slave_cli)
        self._ativo = True
        threading.Thread(target=self._ponte, daemon=True).start()

    def _ponte(self) -> None:
        fds = (self._master_sim, self._master_cli)
        while self._ativo:
            prontos, _, _ = select.select(fds, [], [], 0.2)
            for fd in prontos:
                try:
                    dados = os.read(fd, 4096)
                except OSError:
                    return
                destino = self._master_cli if fd == self._master_sim else self._master_sim
                try:
                    os.write(destino, dados)
                except OSError:
                    return

    def fechar(self) -> None:
        self._ativo = False
        time.sleep(0.25)
        for fd in (*self._slaves, self._master_sim, self._master_cli):
            try:
                os.close(fd)
            except OSError:
                pass


class Controlador:
    """Cliente serial que espera a resposta terminar, como um driver real."""

    def __init__(self, porta: str) -> None:
        import serial

        self.serial = serial.Serial(porta, baudrate=9600, timeout=0.2)

    def envia(self, comando: str, timeout: float = 10.0) -> str:
        self.serial.reset_input_buffer()
        self.serial.write(f"{comando} ".encode("ascii"))
        self.serial.flush()

        linhas: list[str] = []
        pendente = b""
        limite = time.monotonic() + timeout
        while time.monotonic() < limite:
            char = self.serial.read(1)
            if not char:
                continue
            pendente += char
            if not pendente.endswith(b"\n"):
                continue
            linha = pendente.decode("ascii", errors="ignore").strip()
            pendente = b""
            if linha:
                linhas.append(linha)
            if linha.startswith(("*", "!")):
                return "\n".join(linhas)
        raise TimeoutError(f"sem resposta para '{comando}' em {timeout}s")

    def numero(self, comando: str) -> float:
        resposta = self.envia(comando)
        ultima = resposta.splitlines()[-1] if resposta else ""
        if not ultima.startswith("*"):
            raise RuntimeError(f"resposta inesperada para '{comando}': {resposta!r}")
        return float(ultima[1:].strip())

    def fechar(self) -> None:
        self.serial.close()


def executa(relatorio: Relatorio, controlador: Controlador, device) -> None:
    print("\n[1/6] Enlace e identificação")
    controlador.envia("ED")   # eco desligado
    controlador.envia("FT")   # feedback terso
    versao = controlador.envia("V")
    relatorio.checa("Responde à consulta de versão (V)", versao.startswith("*"), versao.strip())

    print("\n[2/6] Resolução e limites de curso")
    res_pan = controlador.numero("PR")
    res_tilt = controlador.numero("TR")
    relatorio.checa(
        "Resolução (PR/TR) confere com o dispositivo",
        abs(res_pan - device.pan.arcsec_per_count) < 1e-3
        and abs(res_tilt - device.tilt.arcsec_per_count) < 1e-3,
        f'pan {res_pan}"/cont · tilt {res_tilt}"/cont',
    )
    cont_por_grau = 3600.0 / res_pan
    minimo, maximo = controlador.numero("PN"), controlador.numero("PX")
    relatorio.checa(
        "Limites de curso (PN/PX) coerentes",
        minimo < 0 < maximo,
        f"{minimo/cont_por_grau:.1f}° a {maximo/cont_por_grau:.1f}°",
    )

    print("\n[3/6] Movimento comandado e aguardado (PS/PP/A)")
    controlador.envia(f"PS{int(40 * cont_por_grau)}")
    controlador.envia(f"TS{int(40 * 3600.0 / res_tilt)}")
    alvo_pan = int(45.0 * cont_por_grau)
    inicio = time.monotonic()
    controlador.envia(f"PP{alvo_pan}")
    controlador.envia("A", timeout=60.0)
    decorrido = time.monotonic() - inicio
    alcancado = controlador.numero("PP")
    relatorio.checa(
        "Chegou na posição comandada (45°)",
        abs(alcancado - alvo_pan) <= 1,
        f"{alcancado/cont_por_grau:.2f}° em {decorrido:.1f}s",
    )
    relatorio.checa(
        "Movimento levou tempo compatível com a velocidade",
        0.5 < decorrido < 10.0,
        f"{decorrido:.1f}s para 45° a 40°/s",
    )

    print("\n[4/6] Movimento combinado dos dois eixos (B)")
    alvo_tilt = int(-20.0 * 3600.0 / res_tilt)
    velocidade = int(40 * cont_por_grau)
    controlador.envia(f"B0,{alvo_tilt},{velocidade},{velocidade}")
    controlador.envia("A", timeout=60.0)
    relatorio.checa(
        "Pan e tilt chegaram juntos ao alvo",
        abs(controlador.numero("PP")) <= 1 and abs(controlador.numero("TP") - alvo_tilt) <= 1,
        "pan 0° · tilt -20°",
    )

    print("\n[5/6] Parada de emergência (H)")
    controlador.envia(f"PS{int(8 * cont_por_grau)}")
    controlador.envia(f"PP{int(120 * cont_por_grau)}")
    time.sleep(0.4)
    movendo = device.pan.is_in_motion()
    controlador.envia("H")
    time.sleep(0.3)
    parado_em = device.pan.position
    time.sleep(0.4)
    relatorio.checa("Estava em movimento antes do halt", movendo)
    relatorio.checa(
        "Halt parou o eixo e ele não voltou a andar",
        device.pan.position == parado_em and not device.pan.is_in_motion(),
        f"parou em {parado_em/cont_por_grau:.2f}°",
    )

    print("\n[6/6] Limites de usuário são respeitados (PNU/PXU/LU)")
    controlador.envia(f"PNU{int(-10 * cont_por_grau)}")
    controlador.envia(f"PXU{int(10 * cont_por_grau)}")
    controlador.envia("LU")
    controlador.envia(f"PP{int(90 * cont_por_grau)}")
    alvo_truncado = controlador.numero("PO")
    relatorio.checa(
        "Comando fora de faixa foi truncado no limite",
        abs(alvo_truncado - 10 * cont_por_grau) <= 1,
        f"pediu 90°, alvo virou {alvo_truncado/cont_por_grau:.2f}°",
    )
    controlador.envia("LE")


def main() -> int:
    if os.name != "posix":
        print(
            "Este autoteste usa PTYs (Linux/macOS). No Windows, rode 'pytest' e o\n"
            "teste manual com com0com descrito em docs/PROCEDIMENTO.md.",
            file=sys.stderr,
        )
        return 2

    print("=" * 62)
    print("AUTOTESTE DO SIMULADOR PTU-D300E")
    print("=" * 62)

    par = ParSerialVirtual()
    device = build_device(update_hz=100.0)
    protocolo = DPCLProtocol(device, await_timeout=60.0)
    servidor = SerialServer(
        SerialTransport(SerialTransportConfig(port=par.porta_simulador, baudrate=9600)),
        protocolo,
    )

    print(f"\nSimulador   : {par.porta_simulador}")
    print(f"Controlador : {par.porta_controlador}")

    device.start()
    servidor.start()
    time.sleep(0.3)

    relatorio = Relatorio()
    controlador = None
    try:
        controlador = Controlador(par.porta_controlador)
        executa(relatorio, controlador, device)
    except Exception as exc:
        relatorio.checa(f"Execução sem erros ({type(exc).__name__})", False, str(exc))
    finally:
        if controlador is not None:
            controlador.fechar()
        servidor.stop()
        device.stop()
        par.fechar()

    return relatorio.resumo()


if __name__ == "__main__":
    sys.exit(main())
