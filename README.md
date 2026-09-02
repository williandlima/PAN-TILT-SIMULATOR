# Simulador do Pan-Tilt PTU-D300E (RS-485 / USB)

Simulador em Python do pan-tilt **PTU-D300E** (FLIR / Directed
Perception), que fala o protocolo ASCII de comando do fabricante (DPCL —
*Pan-Tilt Command Language*) por porta serial, e mostra graficamente
(PyQt5) o movimento de pan e tilt de uma unidade com antena helicoidal
acoplada, em tempo real, conforme os comandos recebidos.

Funciona tanto como ferramenta de **desenvolvimento/teste** de um
controlador que fala com o PTU real (você aponta seu software cliente
para a porta serial do simulador, no PC ou na BeagleBone, no lugar do
hardware), quanto como **demonstração visual** de como a unidade se
comportaria.

![status](https://img.shields.io/badge/status-em%20desenvolvimento-orange)

## Funcionalidades

1. Protocolo ASCII do fabricante (DPCL) implementado em `pantiltsim/protocol.py`
   — comandos de posição, velocidade, aceleração, limites de curso e de
   velocidade, modos de controle (posição/velocidade), eco, feedback
   terso/verboso, reset, save/restore de configurações. Veja
   [`docs/PROTOCOL.md`](docs/PROTOCOL.md) para a lista completa e as
   fontes usadas para validar o protocolo.
2. Comunicação via **RS-485** (com toggle automático de RTS via
   `pyserial`, para adaptadores que suportam `RS485Settings`) e via
   **USB** (porta serial virtual) — o mesmo código de protocolo funciona
   nos dois casos, pois ambos aparecem como uma porta serial para o
   sistema operacional.
3. Roda em **Linux/BeagleBone** (inclusive sem monitor, modo
   `--headless`) e em **Windows/notebook** (GUI ou headless).
4. Interface gráfica em **PyQt5** com desenho vetorial animado da
   unidade pan-tilt com antena helicoidal acoplada, atualizado em tempo
   real conforme a posição muda.
5. Painel mostrando a posição atual e o alvo de pan/tilt, atualizados
   conforme os valores recebidos via RS-485/USB seguindo o protocolo do
   fabricante (ou via controle manual pela própria GUI, que usa o mesmo
   caminho de comando ASCII internamente).
6. Cobre as principais funcionalidades de controle do PTU-D300E:
   posicionamento absoluto e relativo, controle de velocidade/aceleração,
   modo de velocidade contínua, limites de curso configuráveis, halt,
   reset e consulta de status — ver limitações documentadas em
   `docs/PROTOCOL.md`.

## Instalação

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Dependências: `pyserial` (comunicação serial) e `PyQt5` (interface
gráfica — necessária apenas para o modo `--gui`).

## Uso

### Interface gráfica

```bash
python3 -m pantiltsim.main --gui
# ou simplesmente:
python3 -m pantiltsim.main
```

Na GUI:
- **Conexão**: escolha a porta serial (botão "Atualizar" relista as
  portas disponíveis), o tipo de interface (USB ou RS-485) e o baud rate,
  depois clique em "Conectar". A partir daí, comandos DPCL recebidos por
  essa porta (de um controlador real ou de outro programa) movem a
  unidade simulada e aparecem no log.
- **Controle manual**: mesmo sem conectar uma porta serial, dá para
  mover a unidade simulada diretamente pela GUI (spinboxes de pan/tilt,
  botões de jog, halt, reset) — os cliques disparam os mesmos comandos
  ASCII (`PP`, `TP`, `PS`, `TS`, `H`, `R`, ...) internamente, visíveis no
  log do protocolo.
- **Log do protocolo**: mostra cada comando recebido e a resposta
  enviada, útil para depurar um cliente/controlador real.

### Modo headless (sem tela — ex.: BeagleBone via SSH)

```bash
python3 -m pantiltsim.main --headless --port /dev/ttyUSB0 --baud 9600
python3 -m pantiltsim.main --headless --port /dev/ttyUSB0 --baud 9600 --rs485
```

Imprime cada comando recebido e a posição atual periodicamente no
terminal. `Ctrl+C` encerra.

### Listar portas seriais disponíveis

```bash
python3 -m pantiltsim.main --list-ports
```

## Testando localmente sem hardware serial real

Para testar um controlador de verdade contra o simulador sem precisar de
um adaptador RS-485/USB físico, crie um par de portas seriais virtuais
ligadas uma na outra e aponte o simulador para uma ponta e o seu
controlador para a outra:

- **Linux**: `socat -d -d pty,raw,echo=0,link=/tmp/ptu-sim pty,raw,echo=0,link=/tmp/ptu-cliente`
- **Windows**: [com0com](https://sourceforge.net/projects/com0com/) cria
  um par de portas COM virtuais (ex.: `COM10`↔`COM11`).

## Estrutura do projeto

```
pantiltsim/
  device.py           # Máquina de estados do PTU (posição, velocidade, limites, modos)
  protocol.py          # Parser/executor do protocolo ASCII DPCL do fabricante
  transport_serial.py  # Transporte serial (RS-485 / USB) via pyserial
  app_cli.py            # Modo headless (console)
  main.py                # Ponto de entrada (--gui / --headless / --list-ports)
  gui/
    main_window.py        # Janela principal (conexão, controle manual, log)
    pantilt_widget.py      # Desenho vetorial animado do PTU + antena helicoidal
docs/
  PROTOCOL.md           # Especificação do protocolo, fontes e limitações
tests/
  test_device.py        # Testes da simulação de movimento
  test_protocol.py       # Testes do parser/executor de comandos
```

## Testes

```bash
pip install pytest
pytest
```

## Sobre a fidelidade ao protocolo real

O acesso automatizado aos PDFs oficiais do *Command Reference Manual* da
FLIR foi bloqueado pela política de rede do ambiente onde este projeto
foi desenvolvido. A estrutura do protocolo (formato de comando, formato
de resposta numérica e a resposta de reset) foi verificada lendo o
código-fonte de um driver de código aberto que fala com hardware PTU
real; os demais comandos seguem a nomenclatura publicamente documentada
da família DPCL. Veja [`docs/PROTOCOL.md`](docs/PROTOCOL.md) para os
detalhes, as fontes tentadas/confirmadas e o que ajustar caso você tenha
acesso ao manual oficial do seu PTU-D300E e precise de fidelidade
numérica exata (resolução de encoder, curso e velocidades máximas variam
conforme a configuração do equipamento pedido).
