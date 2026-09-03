# Procedimento de instalação, teste e utilização

Simulador do Pan-Tilt **PTU-D300E** (RS-485 / USB).

Todos os comandos e saídas deste documento foram executados e conferidos.
Onde aparece "saída esperada", é a saída real do programa.

---

## 1. Antes de começar

| Item | Requisito |
|------|-----------|
| Python | 3.9 ou superior |
| Dependência obrigatória | `pyserial` (instalada automaticamente) |
| Dependência da interface gráfica | `PyQt5` (só no modo `--gui`) |
| Sistemas | Linux (inclusive BeagleBone), Windows |
| Hardware | **Nenhum** para testar; conversor RS-485 ou cabo USB para uso real |

Decida antes qual modo você vai usar, porque muda o que instalar:

- **Com interface gráfica** (notebook Windows/Linux): instale o extra `gui`.
- **Sem monitor** (BeagleBone via SSH): instale só o núcleo — é bem mais leve.

---

## 2. Instalação

### 2.1 Linux e BeagleBone

```bash
git clone https://github.com/williandlima/PAN-TILT-SIMULATOR.git
cd PAN-TILT-SIMULATOR

python3 -m venv .venv
source .venv/bin/activate

pip install -e ".[gui]"     # com interface gráfica
# ou, na BeagleBone sem monitor:
pip install -e .            # só o núcleo (pyserial)
```

Se você já tem o repositório baixado, pule o `git clone` e comece pelo `cd`.

### 2.2 Windows (PowerShell)

> **Cole uma linha por vez.** O PowerShell junta um bloco colado inteiro em um
> único comando: se a primeira linha falhar, **nenhuma** das seguintes roda —
> e você fica achando que instalou quando nada aconteceu.

```powershell
git clone https://github.com/williandlima/PAN-TILT-SIMULATOR.git
cd PAN-TILT-SIMULATOR
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[gui]"
```

Se você já tem o repositório baixado, pule o `git clone` e comece pelo `cd`.

Use a forma `.\.venv\Scripts\Activate.ps1` (com o `.\` na frente): é o script de
ativação do PowerShell. O `activate` sem extensão é a versão de Linux e o
`activate.bat` é a do `cmd.exe` — nenhum dos dois ativa corretamente uma sessão
do PowerShell.

Se o `Activate.ps1` falhar com *"a execução de scripts foi desabilitada neste
sistema"*, libere só para esta janela e ative de novo:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### 2.3 Permissão de acesso à porta serial (Linux)

Sem isso, abrir a porta falha com *Permission denied*:

```bash
sudo usermod -a -G dialout $USER
```

Saia e entre na sessão de novo (ou reinicie) para o grupo valer.

### 2.4 Verificação da instalação

```bash
ptu-sim --version
ptu-sim --list-ports
```

Saída esperada (a lista de portas varia conforme a máquina):

```
pantiltsim 0.2.0
/dev/ttyS0	n/a
```

Se `ptu-sim` não for encontrado, o ambiente virtual não está ativo — reative
com `source .venv/bin/activate` (Linux) ou `.venv\Scripts\activate`
(Windows), ou use a forma equivalente `python3 -m pantiltsim.main ...`.

---

## 3. Teste

Três níveis, do mais rápido ao mais completo. Faça pelo menos o 3.1.

### 3.1 Autoteste (1 comando, sem hardware) — Linux/macOS

Cria um par de portas seriais virtuais, sobe o simulador de um lado e, do
outro, executa a mesma sequência que um controlador real executaria.

```bash
python3 tools/autoteste.py
```

Saída esperada:

```
==============================================================
AUTOTESTE DO SIMULADOR PTU-D300E
==============================================================

Simulador   : /dev/pts/0
Controlador : /dev/pts/1

[1/6] Enlace e identificação
  [PASSOU] Responde à consulta de versão (V)  (* PTU-D300E Simulator v0.2.0 - DPCL compatible)

[2/6] Resolução e limites de curso
  [PASSOU] Resolução (PR/TR) confere com o dispositivo  (pan 23.1428"/cont · tilt 23.1428"/cont)
  [PASSOU] Limites de curso (PN/PX) coerentes  (-159.0° a 159.0°)

[3/6] Movimento comandado e aguardado (PS/PP/A)
  [PASSOU] Chegou na posição comandada (45°)  (45.00° em 1.8s)
  [PASSOU] Movimento levou tempo compatível com a velocidade  (1.8s para 45° a 40°/s)

[4/6] Movimento combinado dos dois eixos (B)
  [PASSOU] Pan e tilt chegaram juntos ao alvo  (pan 0° · tilt -20°)

[5/6] Parada de emergência (H)
  [PASSOU] Estava em movimento antes do halt
  [PASSOU] Halt parou o eixo e ele não voltou a andar  (parou em 2.55°)

[6/6] Limites de usuário são respeitados (PNU/PXU/LU)
  [PASSOU] Comando fora de faixa foi truncado no limite  (pediu 90°, alvo virou 10.00°)

==============================================================
RESULTADO: 9/9 itens passaram — simulador operacional
```

O código de saída é `0` em caso de sucesso, então dá para usar em script
de verificação: `python3 tools/autoteste.py && echo OK`.

### 3.2 Suíte automatizada

```bash
pip install -e ".[dev]"
pytest
```

Saída esperada:

```
............................................                             [100%]
44 passed in 10.53s
```

O que cada arquivo cobre:

| Arquivo | Cobertura |
|---------|-----------|
| `tests/test_device.py` | Física do movimento, limites, micropasso, modos de controle |
| `tests/test_protocol.py` | Cada comando e os formatos exatos de resposta |
| `tests/test_end_to_end_serial.py` | Transporte + protocolo + movimento **por uma porta serial real** |

**No Windows o resultado é `37 passed, 7 skipped`**, e está correto: os 7 testes
ponta a ponta usam PTYs, que só existem em Linux/macOS, então são pulados. Para
cobrir esse caminho no Windows, use o par de portas virtuais do com0com
(seção 3.4). Pelo mesmo motivo, o autoteste da seção 3.1 não roda no Windows —
lá a verificação visual equivalente é o roteiro da seção 3.3.

### 3.3 Teste manual da interface gráfica

```bash
ptu-sim --gui
```

> **No VS Code, não use o botão ▶️ "Run Python File".** Esse botão executa o
> arquivo aberto diretamente (`python arquivo.py`); este projeto usa import
> relativo entre módulos (`pantiltsim/main.py` importa com `from . import`),
> que só funciona rodando como pacote — com `-m` ou com o `ptu-sim`
> instalado. Rodar o arquivo direto dá erro de import relativo.
>
> O repositório já traz `.vscode/launch.json` com o jeito certo: abra o
> painel **Run and Debug** (`Ctrl+Shift+D`) e escolha **Simulador PTU-D300E
> (GUI)** na lista, ou tecle `F5`. Isso roda `python -m pantiltsim.main
> --gui` de verdade, com o interpretador do `.venv`. Há também uma opção
> **(headless)** — pede a porta serial — e **Autoteste (sem hardware)**.

Roteiro de verificação:

1. **Aba Controle** → digite `45` em *Pan alvo*, `20` em *Tilt alvo*, clique
   em **Ir para posição**. A unidade 3D deve girar suavemente até a
   posição, a bússola de pan e o arco de tilt acompanharem, e o rótulo
   mudar de `EM MOVIMENTO` para `EM POSIÇÃO`.
2. **Telemetria** → confira que *Pan* mostra `45.00°` e as contagens
   correspondentes, e que *Resolução* está preenchida.
3. **Halt** → mande um movimento longo (ex.: pan `-150`) e clique em
   **Halt (H)** no meio do caminho: o movimento tem de parar na hora.
4. **Aba Terminal DPCL** → digite `PR` e confirme a resposta
   `* Pan resolution per position is 23.1428`. Depois digite `PP1000` e veja
   a unidade se mover.
5. **Modo monitor** → marque *Modo monitor / auto-scan*: a unidade deve
   varrer sozinha entre os limites. Desmarque para parar.
6. **Aba Configuração** → troque *Micropasso* para `Quarter step` e volte à
   telemetria: a resolução tem de mudar, **sem** a unidade sair do lugar
   (o ângulo físico é preservado; só a unidade de contagem muda).

### 3.4 Teste com portas seriais virtuais (dois programas separados)

Para exercitar o simulador com o **seu** software, sem hardware.

**Linux** — com `socat` (instale com `sudo apt install socat`):

```bash
# terminal 1: cria o par de portas ligadas uma na outra
socat -d -d pty,raw,echo=0,link=/tmp/ptu-sim pty,raw,echo=0,link=/tmp/ptu-cliente

# terminal 2: o simulador em uma ponta
ptu-sim --gui                      # e conecte em /tmp/ptu-sim pela interface
# ou: ptu-sim --headless --port /tmp/ptu-sim

# terminal 3: o seu software (ou o cliente de exemplo) na outra ponta
python3 tools/ptu_client.py --port /tmp/ptu-cliente --demo
```

**Windows** — instale o [com0com](https://sourceforge.net/projects/com0com/),
que cria um par de portas COM virtuais (ex.: `COM10` ↔ `COM11`). Aponte o
simulador para uma e o seu software para a outra.

Saída esperada do `--demo`:

```
Preparando o enlace (eco desligado, feedback terso)...
Resolução: pan 23.1428"/contagem · tilt 23.1428"/contagem
Curso pan: -24733 .. 24733 contagens
Ajustando velocidade para 6222 contagens/s ...
Movendo para pan=45.0° tilt=20.0° ... chegou em 45.00° / 20.00° em 1.8s
Movendo para pan=-60.0° tilt=-15.0° ... chegou em -60.00° / -15.00° em 3.3s
Movendo para pan=0.0° tilt=0.0° ... chegou em 0.00° / 0.00° em 2.1s
```

### 3.5 Teste com fiação real (RS-485 ou USB)

Com dois conversores ligados no mesmo barramento — um na máquina do
simulador, outro na do controlador:

```bash
# na máquina do simulador
ptu-sim --headless --port /dev/ttyUSB0 --baud 9600 --rs485

# na máquina do controlador
python3 tools/ptu_client.py --port /dev/ttyUSB1 --rs485 --demo
```

Confirme os dois lados com a **mesma** velocidade, paridade e bits de
parada (padrão: 9600 8N1). Em RS-485, confira também a polaridade A/B e
os resistores de terminação (120 Ω nas duas pontas do barramento).

---

## 4. Utilização

### 4.1 Interface gráfica (notebook Windows/Linux)

```bash
ptu-sim --gui
```

1. Em **Conexão**, escolha a porta (botão *Atualizar* relista), o tipo de
   interface (*USB / RS-232* ou *RS-485 half-duplex*) e o baud rate.
2. Clique em **Conectar**. A partir daí, comandos que chegarem por essa
   porta movem a unidade simulada e aparecem no log.
3. Sem conectar nenhuma porta, o simulador continua utilizável em modo
   local: os controles da interface funcionam do mesmo jeito.

Deixar *Reconectar automaticamente* marcado faz o simulador reabrir a
porta sozinho se o cabo/dongle cair.

### 4.2 Modo headless (BeagleBone via SSH)

```bash
ptu-sim --headless --port /dev/ttyUSB0 --baud 9600
ptu-sim --headless --port /dev/ttyS4  --baud 9600 --rs485   # UART nativa
```

Saída esperada:

```
21:12:30 INFO    pantiltsim.device: Motor de simulação iniciado (50 Hz)
21:12:30 INFO    pantiltsim.transport_serial: Porta /dev/pts/0 aberta a 9600 bps (USB/RS-232)
21:12:30 INFO    pantiltsim.app_cli: Simulador PTU-D300E ativo em /dev/pts/0 (USB/RS-232, 9600 bps). Ctrl+C para sair.
21:12:30 INFO    pantiltsim.app_cli: pan=   0.00° (0) tilt=   0.00° (0) parado
21:12:32 INFO    pantiltsim.app_cli: PR -> PR
* Pan resolution per position is 23.1428
```

Cada comando recebido e a posição atual vão para o log. `Ctrl+C` encerra.
Use `--log-level debug` para ver mais detalhe.

Na BeagleBone, a UART precisa estar habilitada no device tree antes de
aparecer como porta; o nome varia conforme a versão do kernel
(`/dev/ttyO4` nos mais antigos, `/dev/ttyS4` nos mais novos). Confirme com
`ptu-sim --list-ports`. Em RS-485, o controle de direção normalmente é
feito por RTS — é o que a opção `--rs485` habilita; se o seu adaptador
faz isso em hardware, o simulador avisa no log e segue funcionando.

### 4.3 Integrando o seu software

Sequência recomendada, a mesma que os drivers reais usam:

```
1. Abrir a porta serial (9600 8N1 por padrão)
2. Enviar  ED    -> desliga o eco (respostas ficam limpas)
3. Enviar  FT    -> feedback terso: respostas viram "* <valor>"
4. Enviar  PR    -> resolução do pan, em segundos de arco por contagem
5. Enviar  TR    -> resolução do tilt
6. Calcular      -> contagens_por_grau = 3600 / resolução
```

A partir daí, o ciclo de trabalho:

| Objetivo | Comando |
|----------|---------|
| Definir velocidade | `PS<contagens/s>` e `TS<contagens/s>` |
| Ir para uma posição | `PP<contagens>` e `TP<contagens>` |
| Mover os dois de uma vez | `B<pan>,<tilt>,<vel_pan>,<vel_tilt>` |
| Esperar o movimento acabar | `A` (só responde quando termina) |
| Ler a posição atual | `PP` e `TP` (sem valor) |
| Ler a posição alvo | `PO` e `TO` |
| Parar tudo | `H` |

**Importante:** não leia a resposta com um `sleep` de tempo fixo. Leia até
chegar a linha que começa com `*` (sucesso) ou `!` (erro) — é o que mantém
o enlace sincronizado em comandos demorados como o `A`. O
`tools/ptu_client.py` mostra exatamente como fazer isso e serve de ponto
de partida; o mesmo código funciona apontado para o equipamento real.

Tabela completa de comandos: [`PROTOCOL.md`](PROTOCOL.md).

### 4.4 Ajustando para o seu equipamento

Resolução, curso e velocidades variam conforme a redução e o encoder da
unidade encomendada. Crie um arquivo com os números da **sua** unidade:

```json
{
  "model_name": "PTU-D300E",
  "pan":  { "full_step_arcsec": 185.1428, "factory_min_deg": -159.0, "factory_max_deg": 159.0 },
  "tilt": { "factory_min_deg": -90.0, "factory_max_deg": 30.0, "max_speed_deg_per_sec": 40.0 }
}
```

```bash
ptu-sim --gui --config meu_ptu.json
```

Os valores default são plausíveis para a família, mas **não** são os de
fábrica de uma unidade específica — confira na etiqueta/datasheet do seu
equipamento antes de usar o simulador para validar tempos e cursos.

---

## 5. Resolução de problemas

| Sintoma | Causa provável | O que fazer |
|---------|----------------|-------------|
| PowerShell: `Operador '<' reservado para uso futuro` | Um marcador `<...>` foi digitado literalmente; `<` é operador reservado | Substitua o marcador pelo valor real. As instruções da seção 2.2 já usam a URL de verdade |
| PowerShell: colei o bloco e "nada aconteceu" | O bloco colado vira um comando só; se a linha 1 falha, nenhuma outra roda | Cole **uma linha por vez** e confira o resultado de cada uma |
| PowerShell: *"a execução de scripts foi desabilitada neste sistema"* | Política de execução bloqueia o `Activate.ps1` | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` e ative de novo |
| PowerShell: `O termo '/c:/…/python.exe' não é reconhecido` | Caminho em formato Unix; no Windows é `C:\…` com barras invertidas | Com o venv ativo (prefixo `(.venv)` no prompt) **não use caminho nenhum**: rode só `pip install -e ".[gui]"` |
| Apareceu uma pasta `.venv-1` além da `.venv` | Um segundo ambiente foi criado com a `.venv` já existente (típico do *Python: Create Environment* do VS Code) | Fique com um só. Veja qual está ativo com `python -c "import sys; print(sys.executable)"` e apague o outro |
| `ptu-sim: command not found` | Ambiente virtual não ativado | `source .venv/bin/activate` ou use `python3 -m pantiltsim.main` |
| VS Code: botão ▶️ "Run Python File" não abre nada / erro de import relativo | O botão executa o arquivo aberto direto (`python arquivo.py`), e o projeto usa import relativo entre módulos | Use `F5` (Run and Debug) com a configuração **Simulador PTU-D300E (GUI)** já incluída em `.vscode/launch.json`, ou rode pelo terminal (`ptu-sim --gui`) |
| `A interface gráfica precisa do PyQt5` | Instalado só o núcleo | `pip install "pantiltsim[gui]"`, ou use `--headless` |
| `Permission denied` ao abrir a porta | Usuário fora do grupo `dialout` | `sudo usermod -a -G dialout $USER` e reabra a sessão |
| Porta não aparece em `--list-ports` | Driver/cabo/UART não habilitada | Confira o cabo; na BeagleBone habilite a UART no device tree |
| Conecta mas nada responde | Baud/paridade diferentes, ou A/B trocados no RS-485 | Iguale os dois lados (9600 8N1); inverta A/B; confira a terminação 120 Ω |
| Respostas embaralhadas ou fora de ordem | Cliente lendo com `sleep` fixo | Leia até a linha começada por `*` ou `!` (ver 4.3) |
| Cliente trava depois de um `A` | Timeout de leitura menor que o movimento | Aumente o timeout do cliente; o `A` só responde ao terminar |
| Movimento não chega ao ângulo pedido | Limite de curso truncou o alvo | Consulte `PN`/`PX`; ajuste com `PNU`/`PXU` + `LU`, ou `LD` para desabilitar |
| Contagens "mudaram sozinhas" | Micropasso alterado (`WP`/`WT`) | Comportamento correto: o ângulo é preservado, a unidade de contagem muda. Releia `PR` |

---

## 6. Referência rápida

```bash
ptu-sim --gui                                    # interface gráfica
ptu-sim --headless --port /dev/ttyUSB0           # sem monitor
ptu-sim --headless --port /dev/ttyO4 --rs485     # RS-485
ptu-sim --list-ports                             # portas disponíveis
ptu-sim --gui --config meu_ptu.json              # com parâmetros próprios
ptu-sim --headless --port X --log-level debug    # log detalhado

python3 tools/autoteste.py                       # autoteste de aceitação
python3 tools/ptu_client.py --port X --demo      # demonstração
python3 tools/ptu_client.py --port X             # terminal interativo
pytest                                           # suíte automatizada
```

Documentos relacionados: [`../README.md`](../README.md) (visão geral) e
[`PROTOCOL.md`](PROTOCOL.md) (protocolo completo, com o que foi
confirmado contra hardware real).
