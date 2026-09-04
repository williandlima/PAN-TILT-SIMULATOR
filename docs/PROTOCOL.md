# Protocolo implementado (DPCL — Pan-Tilt Command Language)

O PTU-D300E (Teledyne FLIR / Directed Perception, linha "E-Series", que
também inclui PTU-D46, PTU-D48E e PTU-D100E) é controlado por um conjunto
de comandos ASCII conhecido como **DPCL** — o mesmo conjunto básico em
toda a família, o que permite validar o protocolo mesmo sem o PDF oficial
do D300E.

## Como cada comando foi verificado

A documentação oficial da FLIR não pôde ser baixada automaticamente (ver
"Fontes" no fim). Em vez de adivinhar, o protocolo foi verificado contra
**código-fonte de drivers que conversam com hardware PTU real** e, para
os comandos do Geo Pointing Module (seção mais abaixo), contra **fotos
das páginas reais do manual** fornecidas pelo usuário. Cada comando da
tabela abaixo traz o nível de verificação:

| Marca | Significado |
|-------|-------------|
| ✅ | Confirmado: aparece literalmente no código de um driver que fala com PTU real, **ou** em foto da página real do manual |
| 🟡 | Nomenclatura da família DPCL, sem confirmação byte a byte nesta sessão |

**Fontes confirmadas:**

1. **`hmorris94/FLIR-PTU-Python`** (`flirptu/ptu.py`) — driver Python para
   as unidades E-Series. Dele vêm os comandos `PR`/`TR`, `PO`/`TO`,
   `PD`/`TD`, `PNU`/`PXU`/`TNU`/`TXU`, `LU`/`LE`/`LD`, `RP`/`RT`/`RE`,
   `PU`/`TU`, `B`, `@(baud,0,F)`, `A`, `H`, `C`/`CI`/`CV`, `EE`/`ED` e —
   o mais valioso — **os textos exatos das respostas em modo verboso**,
   que aquele driver fatia por offset fixo:

   ```
   "* Current Pan position is "     -> 26 caracteres
   "* Current Tilt position is "    -> 27 caracteres
   "* Target Pan position is "      -> 25 caracteres
   "* Target Tilt position is "     -> 26 caracteres
   ```

2. **`cburbridge/flir_pantilt_d46`** (`src/ptu46_driver.cc`) — driver ROS
   em C++ para PTU-D46. Dele vêm o formato de comando
   `<eixo><código>[valor] `, a sequência de inicialização (`ft`, `ed`,
   `ci`, `ld`, reset), a resposta fixa de reset `!T!T!P!P*` e o formato
   terso `* <valor>` (ele valida `buffer[0] == '*'` e converte o resto).

3. **`usc-clmc/usc-arm-calibration`** (`arm_head_control/flir_cpi/code/ptu.c`)
   — terceiro driver independente (acadêmico, em C), verificado numa
   tentativa posterior de auditoria contra o manual oficial. Confirma o
   mesmo conjunto de comandos de posição/velocidade/limite dos dois
   drivers acima, sem contradições — e não contém nenhum comando de
   geo-posicionamento, reforçando que o recurso Geo-Pointing (ver seção
   "Rastreamento de antena por GPS") não faz parte do protocolo serial.

Os testes em `tests/test_protocol.py` travam esses formatos: se alguém
alterar uma resposta confirmada, o teste quebra.

## Formato geral

```
<comando>        ::= <comando-de-eixo> | <comando-global>
<comando-de-eixo>::= <eixo><código>[valor]<terminador>
<eixo>           ::= "P" | "T"          (não diferencia maiúsculas/minúsculas)
<terminador>     ::= espaço | CR | LF
```

- Sem valor, o comando é uma **consulta**.
- Vários comandos podem vir na mesma linha: `PA3000 TA3000 PS800 TS800 `.
- Resposta de sucesso começa com `*`; erro começa com `!`.
- **Modo terso** (`FT`): `* <valor>` — é o que drivers sérios usam.
- **Modo verboso** (`FV`, padrão de fábrica): `* <frase> <valor>`.
- Com o eco ligado (`EE`, padrão de fábrica), o comando recebido é
  ecoado antes da resposta.

Para máxima compatibilidade, faça como os drivers reais: enviar
`ED` (desliga eco) e `FT` (feedback terso) logo após abrir a porta.

## Comandos de eixo (prefixo `P` = pan, `T` = tilt)

| Comando | | Descrição | Consulta devolve |
|---------|--|-----------|------------------|
| `PP`/`TP` | ✅ | Posição absoluta desejada, em contagens | posição **atual** |
| `PO`/`TO` | ✅ | Deslocamento relativo de posição | posição **alvo** |
| `PS`/`TS` | ✅ | Velocidade desejada (contagens/s) | velocidade alvo |
| `PD`/`TD` | ✅ | Ajuste relativo de velocidade | velocidade **instantânea** |
| `PA`/`TA` | 🟡 | Aceleração (contagens/s²) | aceleração |
| `PB`/`TB` | 🟡 | Velocidade base da rampa | velocidade base |
| `PU`/`TU` | ✅ | Limite superior de velocidade | limite superior |
| `PL`/`TL` | 🟡 | Limite inferior de velocidade | limite inferior |
| `PN`/`TN` | ✅ | — (consulta) | limite **mínimo** de curso vigente |
| `PX`/`TX` | ✅ | — (consulta) | limite **máximo** de curso vigente |
| `PNU`/`TNU` | ✅ | Define limite mínimo de **usuário** | limite mínimo de usuário |
| `PXU`/`TXU` | ✅ | Define limite máximo de **usuário** | limite máximo de usuário |
| `PR`/`TR` | ✅ | — (somente leitura) | **resolução em segundos de arco por contagem** |
| `PM`/`TM` | 🟡 | Potência em movimento: `L`/`R`/`H` | modo atual |
| `PH`/`TH` | 🟡 | Potência parado: `O`/`L`/`R` | modo atual |

`PR`/`TR` é o comando que torna o simulador realmente utilizável por um
driver de verdade: em vez de assumir uma conversão fixa, o cliente
pergunta a resolução e calcula `contagens/grau = 3600 / resolução`.

## Comandos globais

| Comando | | Descrição |
|---------|--|-----------|
| `H` | ✅ | Halt geral (para os dois eixos) |
| `HP` / `HT` | 🟡 | Halt somente do pan / do tilt |
| `A` | ✅ | Aguarda o fim do movimento antes de responder (segura o enlace) |
| `I` / `S` | ✅ | Execução imediata / slaved (com `S`, os movimentos só disparam no `A`) |
| `R` / `RE` | ✅ | Reset de ambos os eixos — resposta fixa `!T!T!P!P*` |
| `RP` / `RT` | ✅ | Reset somente do pan / do tilt |
| `C` / `CI` / `CV` | ✅ | Consulta / modo posição / modo velocidade contínua |
| `F` / `FT` / `FV` | ✅ | Consulta / feedback terso / verboso |
| `E` / `EE` / `ED` | ✅ | Consulta / eco ligado / desligado |
| `L` / `LE` / `LU` / `LD` | ✅ | Consulta / limites de fábrica / de usuário / desabilitados |
| `M` / `ME` / `MD` | ✅ | Consulta / liga / desliga o modo monitor (auto-scan) |
| `DF` / `DS` / `DR` | 🟡 | Padrões de fábrica / salvar / restaurar configurações |
| `WP<modo>` / `WT<modo>` | 🟡 | Micropasso: `F`ull, `H`alf, `Q`uarter, `E`ighth, `A`uto |
| `B<pan>,<tilt>,<vel_pan>,<vel_tilt>` | ✅ | Move os dois eixos em um único comando |
| `@(<baud>,0,F)` | ✅ | Configura a porta serial do host |
| `V` | 🟡 | Versão de firmware |

Atenção a duas pegadinhas de nomenclatura:

- **`LU` significa "limites de usuário"**, não "limite superior". O
  limite superior de velocidade é `PU`/`TU`.
- **`PD`/`TD` não é "posição delta"**: é velocidade — consulta a
  velocidade instantânea e, com valor, aplica um delta na velocidade.

## Comportamentos simulados de verdade

Não são apenas respostas: o simulador tem física e estado.

- **Perfil de movimento trapezoidal** com aceleração, velocidade base e
  limites inferior/superior de velocidade — um `PP` distante leva o
  tempo correspondente, e `PD` devolve a velocidade instantânea real
  durante a rampa.
- **Micropasso altera a resolução** (`WPQ` muda o que `PR` responde) e as
  contagens são reescaladas preservando o ângulo físico — como no
  hardware.
- **Limites de curso** em três modos, aplicados de fato ao movimento:
  um `PP` fora de faixa é truncado no limite vigente.
- **Modo velocidade** (`CV`): o eixo gira continuamente na velocidade de
  `PS`/`TS` até `H` ou até bater no limite.
- **Execução slaved** (`S`): `PP`/`TP` ficam pendentes e os dois eixos
  partem juntos no `A`.
- **Modo monitor** (`ME`): varredura automática entre os limites.
- **`A` segura o enlace** enquanto o movimento não termina — nenhum outro
  comando é processado nesse intervalo, como no equipamento real. Há um
  timeout de segurança (`DPCLProtocol(await_timeout=...)`) para o enlace
  nunca ficar preso para sempre.

## Geo Pointing Module (GPM) — Capítulo 17, confirmado byte a byte

**Esta seção foi reescrita depois de acesso real ao manual**: o usuário
fotografou as páginas 99 e 111 do "E Series Pan-Tilt Command Reference
Manual, Version 6.00 (09/2014)" da FLIR (Capítulo 17: "Geo Pointing
Module"), permitindo confirmar sintaxe e formato de resposta byte a
byte — não mais por indício ou página de suporte indexada. O PDF
completo continua inacessível por este ambiente (ver "Fontes"), mas o
essencial do capítulo foi verificado desta forma.

### O que o GPM realmente é

O GPM guarda a **pose própria da unidade** — onde ela está instalada no
mundo (latitude, longitude, altitude) e como está orientada (roll, pitch,
yaw) — para poder, em conjunto com uma calibração contra pontos de
referência conhecidos, converter coordenadas geográficas em ângulos de
pan/tilt. **Não é** um comando para informar a posição de um alvo em
movimento: os comandos abaixo sempre leem/escrevem a pose da própria
unidade.

### Comandos confirmados (seção 17.3, página 99, e 17.4, página 111)

| Comando | | Descrição | Campo em `GpmPose` |
|---------|--|-----------|---------------------|
| `GL` | ✅ | Latitude própria (graus) | `latitude_deg` |
| `GO` | ✅ | Longitude própria (graus) | `longitude_deg` |
| `GA` | ✅ | Altitude própria (metros, relativa ao nível do mar) | `altitude_m` |
| `GLLA` | ✅ | Latitude, longitude e altitude próprias, juntas | as três |
| `GR` | ✅ | Roll do PTU (graus) | `roll_deg` |
| `GP` | ✅ | Pitch do PTU (graus) | `pitch_deg` |
| `GY` | ✅ | Yaw do PTU (graus) | `yaw_deg` |
| `GRPY` | ✅ | Roll, pitch e yaw do PTU, juntos | as três |
| `GCP` | ✅ | Offset de pitch da câmera/payload (diferença entre a linha de mira do payload e a do PTU) | `camera_pitch_offset_deg` |

✅ = confirmado byte a byte contra fotos das páginas reais do manual.

**Formato**, também confirmado pelo exemplo do manual (seção 17.4.3):

```
<comando><delim>          consulta -> * <valor>
<comando><valor><delim>   define   -> * <valor>       (mesmo formato da consulta!)
```

Isto é uma diferença real em relação aos comandos de posição de eixo
(`PP`/`TP`, ...), cujo `set` responde só `*\r\n`: os comandos GPM
**sempre** respondem com o valor atual, formatado em **6 casas
decimais**, mesmo ao definir. Combinados (`GLLA`, `GRPY`) respondem os
três valores separados por vírgula, na ordem do próprio nome do comando
(`GRPY` = roll,pitch,yaw; por analogia, `GLLA` = latitude,longitude,altitude).

Exemplo literal do manual (página 111), reproduzido em
`tests/test_protocol.py::test_gpm_orientation_matches_manual_worked_example`:

```
GR   * -1.459233
GP   * 3.103816
GY   * 50.042890
GRPY * -1.459233,3.103816,50.042890
GRPY-1.2,3.2,50
GRPY * -1.200000,3.200000,50.000000
GR-1.5
GY20
GRPY * -1.500000,3.200000,20.000000
GCP
GCP * 0.000000
GCP10.3
GCP * 10.300000
```

(a coluna alinhada antes do `*` é só formatação da tabela do PDF — o que
o dispositivo devolve de fato é `* <valor>\r\n`, igual ao resto do DPCL;
com eco ligado, o comando enviado aparece ecoado antes disso.)

### O que ainda não foi confirmado

O capítulo 17 continua além do que foi fotografado até agora — outras
seções cobrem calibração contra pontos de referência (`GC` calibrar,
`GG` apontar/consultar landmark, `GMN` número de landmarks, `GS` status,
`GDR` restaurar última configuração salva) e o que parece ser um modo de
apontamento operacional (`GT` tipo de ponto, `GGD` distância até o
"aim point"). A **função** de cada um foi indicada pelo usuário a partir
do índice/descrição do manual, mas a **sintaxe exata** (formato de
argumento, valores aceitos por `GT`) não foi fotografada ainda — por
isso esses comandos não estão implementados neste simulador. Se você
tiver acesso a essas páginas, é só completar a tabela acima.

### Rastreamento contínuo de um alvo em movimento — recurso da GUI/API, não um comando DPCL

Nenhuma fonte confirmou um comando ASCII do GPM para "aqui está a
posição atual de um alvo em movimento, aponte para lá agora" — pelo
contrário: a FLIR documenta o GPM como calibração de uma **instalação
fixa** contra pontos de referência conhecidos, e páginas de suporte
oficiais (`flir.custhelp.com`) afirmam que o recurso é **"não
recomendado para aplicações aerotransportadas, montadas em veículo, ou
outras plataformas móveis"** — o oposto do cenário de seguir um veículo
em voo.

Por isso, o rastreamento contínuo de um alvo por GPS/telemetria — o
mesmo princípio de uma estação terrena de satélite, aplicado a um
veículo (avião, drone, balão de sondagem, foguete de sondagem) que
transmite sua própria posição — é implementado neste simulador **só
como lógica de aplicação** (`pantiltsim.tracking.GeoTracker`), exposta
pela GUI (aba "Rastreamento GPS") e pela API Python do dispositivo
(`device.geo_tracker`), e **não como comando de fio**. Isso evita
repetir o erro de uma versão anterior desta funcionalidade, que
inventava comandos `GO`/`GX`/`GE`/`GD`/`GA` — os quais colidiam,
inclusive, com os nomes reais confirmados depois (`GO` é longitude,
`GA` é altitude).

O `GeoTracker` usa `device.gpm_pose` (definida pelos comandos reais
acima) como a posição da estação de solo, e um `GeoPoint` de alvo
definido pela GUI ou por código — e recalcula azimute/elevação a cada
atualização do alvo, comandando `PP`/`TP` internamente. O cálculo é
geodésico → ECEF (Earth-Centered, Earth-Fixed) → ENU (East-North-Up,
plano tangente local da estação) no elipsoide WGS84 — o método padrão
de rastreamento de antena, não uma aproximação de Terra plana; ver
`pantiltsim/tracking.py` (`look_angles`) e `tests/test_tracking.py`
para os casos de referência conferidos à mão.

**Isto não é orientação de armas.** O cálculo só resolve "para onde
apontar" a partir de duas posições geográficas — a mesma matemática vale
para qualquer veículo com GPS. Não rastreia, identifica nem interage com
o veículo: apenas converte coordenadas recebidas de uma fonte externa
(um receptor GPS real, ou aqui, para demonstração, o gerador de
trajetória `LinearTrajectory`) num ângulo de apontamento de antena — a
mesma função que uma antena parabólica de estação terrena exerce ao
seguir um satélite.

## Erros

```
! Unknown command 'ZZ'
! Invalid integer value 'abc'
! Resolution is read-only
```

O prefixo `!` é consistente com a única resposta de erro/status
confirmada no hardware (`!T!T!P!P*` do reset); os **textos** das
mensagens são convenção deste simulador.

## Limitações conhecidas

- Os modos de potência (`PM`/`PH`) são registrados e reportados, mas não
  têm efeito físico simulado (torque de retenção, back-drive).
- `LE`/`LU`/`LD` valem para os dois eixos ao mesmo tempo.
- O comando `PO` (offset) é aplicado imediatamente mesmo em modo slaved.
- Não foram implementados o subconjunto **binário** do protocolo nem o
  **Pelco-D**, ambos citados pela FLIR como alternativas suportadas pela
  unidade; aqui só o protocolo ASCII, que é o padrão para RS-232/RS-485/USB.
- Os valores default de resolução, curso e velocidade (em
  `pantiltsim/config.py`) são configuráveis e **não** são os números de
  fábrica de uma unidade específica — eles variam conforme a redução e o
  encoder da unidade encomendada. Ajuste pelo `--config` conforme a
  etiqueta/datasheet do seu equipamento.

## Fontes

Documentos oficiais localizados por busca, mas **bloqueados pela política
de rede** do ambiente de desenvolvimento (baixe-os manualmente para
conferência) — tentativa refeita e confirmada numa sessão posterior,
mesmo resultado:

- `flir.com`, `movitherm.com`, `sustainable-robotics.com`, `archive.org`,
  `studylib.net`, `manualzz.com`, `manualslib.com`, `flir.netx.net`,
  `flir.custhelp.com`, `scribd.com`, `yumpu.com`, `oem.flir.com`,
  `tekgear.com`, `adept.net.au`, `cs.unc.edu`, `web.archive.org`,
  `r.jina.ai`

Fontes efetivamente acessadas e usadas para verificação do protocolo
serial ASCII de posição/velocidade/limites (PP/TP e o restante das
tabelas de comandos de eixo/globais deste documento):

- <https://github.com/hmorris94/FLIR-PTU-Python> — `flirptu/ptu.py`
- <https://github.com/cburbridge/flir_pantilt_d46> — `src/ptu46_driver.cc`
- <https://github.com/usc-clmc/usc-arm-calibration> —
  `arm_head_control/flir_cpi/code/ptu.c` (terceiro driver independente;
  confirma o mesmo conjunto de comandos serial P/T; não implementa o
  Geo Pointing Module — driver acadêmico antigo que simplesmente não
  cobre esse capítulo do manual, o que **não** prova que o GPM esteja
  fora do protocolo serial. Ver correção abaixo.)

**Fonte primária do Geo Pointing Module — fotos das páginas reais do
manual, fornecidas pelo usuário nesta sessão:**

- "E Series Pan-Tilt Command Reference Manual, Version 6.00 (09/2014)",
  Teledyne FLIR Commercial Systems, Inc. — Capítulo 17 "Geo Pointing
  Module", páginas 99 (seção 17.3 "Position and Altitude": comandos
  `GL`/`GO`/`GA`/`GLLA`) e 111 (seção 17.4 "PTU/Camera Orientation":
  comandos `GR`/`GP`/`GY`/`GRPY`/`GCP`, com exemplo de sintaxe completo
  na seção 17.4.3). Este é o mesmo arquivo indexado publicamente como
  `CMD_REF_E_Manual_6.00_PRINT.PDF` — **isto corrige uma conclusão
  anterior desta seção**, que (por falta de acesso ao PDF em si)
  afirmava que o GPM roda só pela interface Ethernet/IP da unidade; na
  verdade os comandos de posição/orientação própria fazem parte do
  mesmo protocolo serial ASCII (DPCL) documentado no resto deste
  arquivo — a interface Ethernet/web citada pelas páginas de suporte
  abaixo é, aparentemente, uma via alternativa/de configuração para o
  mesmo recurso, não a única.

Fontes secundárias sobre o Geo-Pointing, acessadas via trechos indexados
de busca (o texto completo das páginas continua bloqueado pela política
de rede deste ambiente, mas os excertos foram suficientes para confirmar
contexto de uso — calibração, instalação fixa, incompatibilidade com
plataformas móveis):

- `flir.custhelp.com/app/answers/detail/a_id/3233` — "PTU Geo-Pointing
  Functionality"
- `flir.custhelp.com/app/answers/detail/a_id/3393` — "GPM and ISM, GPM
  accuracy"
- `flir.custhelp.com/app/answers/detail/a_id/3146` — "PTU Pan Tilt System
  For Antennas"
- `sustainable-robotics.com/reference/PTU/GPM1.0/PTU-manual-DGPM-V1.0.pdf`
  — "Web Enabled Geo-Pointing Module Model PTU-DGPM USER'S MANUAL Version
  1.0" (localizado, mas não acessado — mesmo bloqueio de rede)
