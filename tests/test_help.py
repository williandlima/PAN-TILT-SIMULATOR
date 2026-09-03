"""Testes da ajuda embutida.

A ajuda mostra números derivados da configuração carregada (resolução,
contagens por grau, curso). Se um desses cálculos quebrar, a janela
falharia só na hora em que o usuário abrisse — daí valer um teste.
"""

import pytest

pytest.importorskip("PyQt5", reason="ajuda faz parte da GUI")

from pantiltsim.config import build_device  # noqa: E402
from pantiltsim.device import StepMode  # noqa: E402
from pantiltsim.gui.help_dialog import _TOPICS, HelpDialog, terminal_help_text  # noqa: E402


def test_every_topic_builds_without_error():
    device = build_device()
    for title, builder in _TOPICS:
        html = builder(device)
        assert html.strip(), f"tópico vazio: {title}"
        assert "<h2>" in html


def test_core_topic_shows_the_loaded_configuration():
    """Os números da ajuda vêm do dispositivo, não são fixos no texto."""
    device = build_device()
    html = dict((t, b) for t, b in _TOPICS)["O núcleo do projeto"](device)

    assert f"{device.pan.arcsec_per_count:.4f}" in html
    assert f"{device.pan.counts_per_degree:.2f}" in html
    assert str(device.pan.deg_to_counts(45.0)) in html


def test_help_follows_step_mode_change():
    device = build_device()
    before = terminal_help_text(device)

    device.pan.set_step_mode(StepMode.QUARTER)
    after = terminal_help_text(device)

    assert before != after
    assert f"{device.pan.counts_per_degree:.2f}" in after


def test_terminal_help_lists_the_essential_commands():
    text = terminal_help_text(build_device())
    for command in ("PP", "PR", "PS", "PNU", "LE", "CV", "ME", "WP", "FT"):
        assert command in text
    assert "contagens por grau" in text


def test_topic_index_is_stable_and_safe():
    assert HelpDialog.topic_index("Modos de teste") == 3
    assert HelpDialog.topic_index("tópico inexistente") == 0
