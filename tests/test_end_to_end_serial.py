"""Teste ponta-a-ponta por uma porta serial de verdade.

Cria um par de PTYs com `os.openpty()` — que o sistema operacional trata
como portas seriais reais — e sobe o simulador completo em uma das
pontas (transporte + protocolo + motor de simulação). Da outra ponta, um
"controlador" fala DPCL por pyserial, exatamente como faria um software
cliente ligado por RS-485 ou USB.

Isso exercita o caminho completo: bytes na porta serial -> parser do
protocolo -> máquina de estados dos eixos -> movimento real -> resposta
de volta pela porta.

Só roda em POSIX (Linux/macOS/BeagleBone); no Windows use um par de
portas virtuais (com0com) para o teste manual equivalente.
"""

from __future__ import annotations

import os
import select
import time

import pytest

pytest.importorskip("serial")

from pantiltsim.config import build_device  # noqa: E402
from pantiltsim.protocol import DPCLProtocol  # noqa: E402
from pantiltsim.transport_serial import (  # noqa: E402
    SerialServer,
    SerialTransport,
    SerialTransportConfig,
)

pytestmark = pytest.mark.skipif(os.name != "posix", reason="requer PTYs POSIX")


class _ClientLink:
    """Controlador na outra ponta do enlace.

    Fala pelo lado *master* do par de PTYs. O simulador abre o lado
    *slave* (``/dev/pts/N``) com pyserial, que é o que o sistema
    apresenta como porta serial — o master só é acessível pelo descritor,
    e não por nome (``os.ttyname`` devolveria ``/dev/ptmx``, que abriria
    um par novo).
    """

    def __init__(self, master_fd: int):
        self.fd = master_fd

    def command(self, text: str, settle: float = 0.15, timeout: float = 2.0) -> str:
        os.write(self.fd, f"{text} ".encode("ascii"))
        time.sleep(settle)
        chunks: list[bytes] = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            ready, _, _ = select.select([self.fd], [], [], 0.05)
            if not ready:
                if chunks:
                    break
                continue
            chunks.append(os.read(self.fd, 4096))
        return b"".join(chunks).decode("ascii", errors="ignore")


@pytest.fixture
def link():
    """Sobe o simulador em uma ponta do PTY e devolve um controlador na outra."""
    master_fd, slave_fd = os.openpty()
    simulator_port = os.ttyname(slave_fd)

    device = build_device(update_hz=100.0)
    protocol = DPCLProtocol(device, await_timeout=10.0)
    transport = SerialTransport(SerialTransportConfig(port=simulator_port, baudrate=9600))
    server = SerialServer(transport, protocol)

    device.start()
    server.start()

    client = _ClientLink(master_fd)
    client.command("ED")   # eco desligado, como fazem os drivers reais
    client.command("FT")   # feedback terso

    try:
        yield client, device
    finally:
        server.stop()
        device.stop()
        os.close(slave_fd)
        os.close(master_fd)


def test_query_resolution_over_serial(link):
    client, device = link
    response = client.command("PR")
    assert response.startswith("*")
    assert float(response[1:].strip()) == pytest.approx(device.pan.arcsec_per_count, abs=1e-3)


def test_move_pan_over_serial_actually_moves(link):
    client, device = link
    target = device.pan.deg_to_counts(30.0)

    assert client.command(f"PS{device.pan.deg_to_counts(60.0)}").startswith("*")
    assert client.command(f"PP{target}").startswith("*")

    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline and device.pan.position != target:
        time.sleep(0.05)

    assert device.pan.position == target
    reported = int(client.command("PP")[1:].strip())
    assert reported == target


def test_await_blocks_until_move_completes(link):
    client, device = link
    client.command(f"PS{device.tilt.deg_to_counts(30.0)}")
    client.command(f"TP{device.tilt.deg_to_counts(20.0)}")

    started = time.monotonic()
    response = client.command("A", settle=0.05)
    elapsed = time.monotonic() - started

    assert response.startswith("*")
    assert elapsed > 0.2  # o await realmente segurou o enlace durante o movimento
    assert not device.tilt.is_in_motion()


def test_halt_over_serial_stops_motion(link):
    client, device = link
    client.command(f"PS{device.pan.deg_to_counts(10.0)}")
    client.command(f"PP{device.pan.deg_to_counts(120.0)}")
    time.sleep(0.3)
    assert device.pan.is_in_motion()

    client.command("H")
    time.sleep(0.2)
    stopped_at = device.pan.position
    time.sleep(0.3)

    assert device.pan.position == stopped_at
    assert not device.pan.is_in_motion()


def test_multiple_commands_in_a_single_write(link):
    client, device = link
    response = client.command("PA3000 TA3000 PS1500 TS1500")
    assert response.count("*") == 4
    assert device.pan.acceleration == 3000
    assert device.tilt.desired_speed == 1500


def test_combined_b_command_moves_both_axes(link):
    client, device = link
    pan_target = device.pan.deg_to_counts(-25.0)
    tilt_target = device.tilt.deg_to_counts(15.0)
    speed = device.pan.deg_to_counts(45.0)

    assert client.command(f"B{pan_target},{tilt_target},{speed},{speed}").startswith("*")

    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline and device.is_in_motion():
        time.sleep(0.05)

    assert device.pan.position == pan_target
    assert device.tilt.position == tilt_target


def test_limits_reject_out_of_range_move_over_serial(link):
    client, device = link
    client.command("PNU-1000 PXU1000 LU")
    client.command("PP9000")

    reported_target = int(client.command("PO")[1:].strip())
    assert reported_target == 1000
