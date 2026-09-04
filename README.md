# Simulador do Pan-Tilt PTU-D300E (RS-485 / USB)

Simulador em Python do pan-tilt **PTU-D300E** (Teledyne FLIR / Directed
Perception) que fala o protocolo ASCII de comando do fabricante (DPCL —
*Pan-Tilt Command Language*) por porta serial, e mostra em tempo real, em
3D, a unidade com uma antena helicoidal acoplada respondendo aos
comandos.

Serve como banco de testes para desenvolver o seu controlador sem o
equipamento na bancada — aponte o software cliente para a porta serial do
simulador (no PC ou na BeagleBone) em vez do hardware — e como
demonstração visual do comportamento do equipamento.

## Funcionalidades

1. **Protocolo do fabricante** (`pantiltsim/protocol.py`): posição
   absoluta e relativa, velocidade, aceleração, velocidade base, limites
   de velocidade, limites de curso de fábrica e de usuário, resolução
   (`PR`/`TR`), modos de controle posição/velocidade, execução
   imediata/slaved, halt por eixo, resets por eixo, monitor/auto-scan,
   micropasso, potência, eco, feedback terso/verboso, movimento
   combinado (`B`) e configuração da porta (`@(baud,0,F)`).
   Os formatos de comando e resposta foram **verificados contra drivers
   de código aberto que conversam com hardware PTU real** — ver
   [`docs/PROTOCOL.md`](docs/PROTOCOL.md).
2. **RS-485 e USB**: o mesmo código de protocolo atende os dois casos
   (o RS-485 liga o half-duplex por RTS do pyserial; o USB é a porta
   serial virtual que a própria unidade expõe), com reconexão automática
   se o cabo cair.
3. **Linux/BeagleBone e Windows**: modo `--gui` e modo `--headless`
   (sem monitor, para rodar via SSH na BeagleBone).
4. **Visualização 3D** (PyQt5 + QPainter, sem dependência 3D externa):
   base, prato giratório, garfo de dois braços, eixo de tilt, placa de
   payload e antena helicoidal — pan e tilt geometricamente corretos,
   com bússola de pan, arco de tilt e indicação do alvo comandado.
5. **Posição mostrada conforme o valor recebido** por RS-485/USB, em
   graus e em contagens, junto com resolução, curso, velocidade
   instantânea e modos ativos.
6. **Comportamento físico simulado**, não só respostas: perfil de
   movimento trapezoidal, limites de curso realmente aplicados,
   micropasso alterando a resolução, `A` (await) segurando o enlace até o
   movimento terminar.
7. **Geo Pointing Module (GPM)** — comandos reais `GL`/`GO`/`GA`/`GLLA`
   (posição própria da unidade) e `GR`/`GP`/`GY`/`GRPY`/`GCP`
   (orientação própria), **confirmados byte a byte** contra fotos do
   Capítulo 17 do manual oficial da FLIR. Por cima disso, uma
   **demonstração de rastreamento contínuo de antena por GPS/telemetria**
   (`pantiltsim/tracking.py`, `device.geo_tracker`) — aponta o pan-tilt
   automaticamente para um alvo em movimento (aeronave, drone, foguete de
   sondagem) a partir da posição GPS da estação de solo e do veículo, com
   geodesia WGS84 completa (geodésico → ECEF → ENU); **não é** um comando
   DPCL, é um recurso de GUI/API deste simulador, já que o GPM real não
   documenta um comando para rastrear alvos móveis. Aba dedicada na GUI,
   com trajetória de demonstração para ver o rastreamento em ação sem
   hardware GPS real — ver [`docs/PROTOCOL.md`](docs/PROTOCOL.md).

## Instalação

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[gui]"            # ou: pip install -r requirements.txt
```

Sem a GUI (BeagleBone headless), `pip install -e .` basta — só o pyserial.

**BeagleBone sem internet no local?** [`deploy/beaglebone/`](deploy/beaglebone/)
traz um instalador offline: as dependências já vêm baixadas no
repositório, então é só copiar a pasta inteira num pendrive e rodar um
script na placa — nenhum acesso à rede necessário na hora.

> **Passo a passo completo de instalação, teste e utilização** (incluindo
> Windows, BeagleBone, instalação offline, teste sem hardware e
> resolução de problemas): [`docs/PROCEDIMENTO.md`](docs/PROCEDIMENTO.md).

Verificação rápida de que está tudo funcionando, sem precisar de hardware:

```bash
python3 tools/autoteste.py     # 9 verificações ponta a ponta, imprime PASSOU/FALHOU
```

## Uso

```bash
ptu-sim --gui                                          # interface gráfica
ptu-sim --headless --port /dev/ttyUSB0 --baud 9600     # BeagleBone via SSH
ptu-sim --headless --port /dev/ttyO4 --rs485           # UART RS-485 nativa
ptu-sim --list-ports                                   # lista as portas
ptu-sim --gui --config meu_ptu.json                    # parâmetros do seu equipamento
```

(ou `python3 -m pantiltsim.main ...` sem instalar o pacote.)

Na GUI:

- **Conexão** — porta, USB ou RS-485, baud rate e reconexão automática.
- **Telemetria** — pan/tilt em graus e contagens, resolução, curso,
  velocidade e modos ativos.
- **Controle** — ir para posição, jog, halt por eixo, reset, await,
  monitor/auto-scan. Cada botão envia comandos DPCL de verdade.
- **Configuração** — micropasso, limites, modos de controle, potência,
  eco, feedback, execução slaved, salvar/restaurar.
- **Rastreamento GPS** — define a posição da estação de solo e do alvo
  (ou gera uma trajetória de demonstração), habilita o apontamento
  automático e mostra azimute/elevação/distância calculados em tempo
  real.
- **Terminal DPCL** — digite comandos crus (`PP1000`, `PR`, `PS`…) e veja
  a resposta, junto com todo o tráfego da porta serial.

Tudo o que a interface faz passa pelo mesmo interpretador do protocolo
usado pela porta serial — mover pela GUI exercita o mesmo caminho de
código que um controlador externo exercitaria.

### Ajuda dentro do programa

- **Menu Ajuda** (ou `F1`) — primeiros passos, o núcleo do projeto, guia da
  interface, modos de teste, rastreamento de antena por GPS e referência
  de comandos. Os números mostrados (resolução, contagens por grau,
  curso) são os da configuração carregada, então continuam corretos com
  `--config`.
- `F2` abre direto os **modos de teste**; `F3`, os **comandos DPCL**; `F4`,
  o **rastreamento de antena por GPS**.
- No **Terminal DPCL**, digite `?` para o resumo dos comandos com a
  conversão graus↔contagens vigente, ou `??` para a janela completa.
- `ptu-sim --help` traz os modos de teste e o essencial do protocolo no
  próprio terminal.

## Cliente de exemplo

`tools/ptu_client.py` é um controlador mínimo que serve tanto para testar
o simulador quanto de referência para o seu software (o mesmo código
funciona apontado para o PTU real):

```bash
python3 tools/ptu_client.py --port /dev/pts/5 --demo     # sequência de demonstração
python3 tools/ptu_client.py --port COM4                  # terminal interativo
python3 tools/ptu_client.py --port COM4 --command PR     # um comando só
```

A sequência `--demo` consulta a resolução com `PR`/`TR`, calcula
contagens/grau, lê os limites, ajusta velocidade, move para três posições
usando `A` (await) e confere a posição alcançada — exatamente o que um
driver real faz.

## Testando sem hardware serial

Crie um par de portas seriais virtuais e ligue simulador e controlador
nas duas pontas:

- **Linux**: `socat -d -d pty,raw,echo=0,link=/tmp/ptu-sim pty,raw,echo=0,link=/tmp/ptu-cliente`
- **Windows**: [com0com](https://sourceforge.net/projects/com0com/) cria
  um par de portas COM virtuais.

A suíte de testes já faz isso automaticamente com PTYs
(`tests/test_end_to_end_serial.py`).

## Configuração do modelo

Resolução, curso e velocidades variam conforme a redução e o encoder da
unidade encomendada — por isso são configuráveis:

```json
{
  "model_name": "PTU-D300E",
  "pan":  { "full_step_arcsec": 185.1428, "factory_min_deg": -159.0, "factory_max_deg": 159.0 },
  "tilt": { "factory_min_deg": -90.0, "factory_max_deg": 30.0, "max_speed_deg_per_sec": 40.0 }
}
```

Ajuste conforme a etiqueta/datasheet do seu equipamento e passe com
`--config`. Os defaults são valores plausíveis da família, **não** os
números de fábrica de uma unidade específica.

## Testes

```bash
pip install -e ".[dev]"
pytest
```

71 testes, em quatro níveis:

- `tests/test_device.py` — física do movimento, limites, micropasso,
  modos.
- `tests/test_protocol.py` — cada comando e os formatos de resposta,
  incluindo os offsets exatos que os drivers reais usam para fatiar as
  respostas verbosas, e os comandos reais do Geo Pointing Module
  (`GL`/`GO`/`GA`/`GLLA`/`GR`/`GP`/`GY`/`GRPY`/`GCP`), com um teste que
  reproduz literalmente o exemplo do manual oficial.
- `tests/test_tracking.py` — a geodesia WGS84 do rastreamento de antena
  (conversão geodésico → ECEF → ENU, azimute/elevação/distância) contra
  casos de referência conferidos à mão.
- `tests/test_end_to_end_serial.py` — **ponta a ponta por uma porta
  serial real** (par de PTYs): um controlador externo consulta resolução,
  comanda movimento, aguarda com `A`, dá halt, envia vários comandos numa
  escrita só e verifica os limites — validando transporte, protocolo e
  motor de simulação juntos.

## Estrutura

```
pantiltsim/
  device.py            # eixos pan/tilt: posição, velocidade, limites, modos
  protocol.py          # interpretador do protocolo ASCII do fabricante
  tracking.py          # geodesia WGS84 do rastreamento de antena por GPS
  transport_serial.py  # porta serial RS-485/USB, com reconexão
  config.py            # parâmetros do modelo (JSON)
  app_cli.py           # modo headless
  main.py              # ponto de entrada
  gui/
    main_window.py     # conexão, telemetria, controle, rastreamento GPS, terminal DPCL
    pantilt_widget.py  # vista principal e instrumentos
    ptu_render.py      # renderizador 3D do PTU com antena helicoidal
tools/ptu_client.py    # controlador de exemplo / referência
docs/PROTOCOL.md       # protocolo, verificação, limitações
```

## Fidelidade ao equipamento real

Os PDFs oficiais da FLIR estavam bloqueados pela política de rede do
ambiente onde este projeto foi desenvolvido. Em vez de adivinhar, o
protocolo foi verificado contra o código-fonte de dois drivers de código
aberto que conversam com unidades PTU físicas — inclusive os textos
exatos das respostas em modo verboso, que aqueles drivers fatiam por
offset fixo. [`docs/PROTOCOL.md`](docs/PROTOCOL.md) marca comando a
comando o que está **confirmado** (✅) e o que segue a nomenclatura da
família sem confirmação byte a byte (🟡), e lista os documentos oficiais
para conferência se você tiver acesso a eles.
