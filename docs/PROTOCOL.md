# Protocolo implementado (DPCL — Pan-Tilt Command Language)

O PTU-D300E (Teledyne FLIR / Directed Perception, linha "E-Series", que
também inclui PTU-D46, PTU-D48E e PTU-D100E) é controlado por um conjunto
de comandos ASCII conhecido como **DPCL** — o mesmo conjunto básico em
toda a família, o que permite validar o protocolo mesmo sem o PDF oficial
do D300E.

## Como cada comando foi verificado

A documentação oficial da FLIR não pôde ser baixada automaticamente (ver
"Fontes" no fim). Em vez de adivinhar, o protocolo foi verificado contra
**código-fonte de drivers que conversam com hardware PTU real**. Cada
comando da tabela abaixo traz o nível de verificação:

| Marca | Significado |
|-------|-------------|
| ✅ | Confirmado: aparece literalmente no código de um driver que fala com PTU real |
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

## Rastreamento de antena por GPS (comandos `G...`, extensão do simulador)

**Atualização desta seção após tentativa de verificação contra o "E
Series Pan-Tilt Command Reference Manual, Version 6.00 (09/2014)"** — o
PDF em si continua inacessível (ver "Fontes" no fim: todo domínio que
hospeda o manual, incluindo `flir.com`, está bloqueado pela política de
rede deste ambiente de desenvolvimento). Mas buscas indexadas trouxeram
trechos de **várias páginas de suporte oficiais da própria FLIR**
(`flir.custhelp.com`) sobre o recurso real de apontamento geográfico, o
que permite corrigir e detalhar o que a seção anterior desta
documentação afirmava apenas por indício fraco:

- O recurso oficial se chama **Geo-Pointing (GPM)** e vem **embutido de
  fábrica** em todas as unidades E-Series (E46, D48E, D100E, **D300E**
  incluído) — não é um acessório separado como uma versão anterior desta
  documentação sugeria.
- Ele funciona sobre a **interface Ethernet/IP embutida da unidade**,
  **não sobre o protocolo serial ASCII (DPCL)** documentado no resto
  deste arquivo — ou seja, arquiteturalmente separado de tudo que este
  simulador implementa via RS-485/USB.
- Exige uma **calibração prévia**: apontar a unidade manualmente para 4
  ou mais pontos de referência (landmarks) de posição conhecida, feito
  pela interface web, para a unidade aprender sua própria posição e
  orientação no mundo real.
- Os parâmetros confirmados são **Lat (graus), Lon (graus), Alt(m)** do
  alvo — três valores, não uma pose completa de 6 graus de liberdade por
  comando como uma sessão de desenvolvimento anterior chegou a suspeitar.
- A própria FLIR documenta que o Geo-Pointing é para **instalações
  fixas**, e **"não recomendado para aplicações aerotransportadas,
  montadas em veículo, ou outras plataformas móveis"** — e é incompatível
  com o módulo de estabilização inercial (ISM) usado nesse tipo de
  instalação.
- Nenhuma fonte acessível (nem as páginas de suporte, nem três drivers de
  código aberto diferentes que implementam o protocolo serial ASCII
  desta família de PTU) trouxe o texto literal de comandos como `GLLA`
  ou `GPRY` — eles seguem **não confirmados**.

**Conclusão da verificação:** o recurso real de geo-apontamento da FLIR
existe e é genuíno, mas é um produto diferente do que este simulador
modela — outra interface de transporte (Ethernet, não serial), outro
fluxo de uso (calibração + coordenada fixa, não telemetria contínua de um
alvo em movimento) e explicitamente não pensado para rastrear um veículo
em voo. O que este módulo do simulador implementa é um **conceito real e
distinto**: uma estação de solo civil de rastreamento de antena de
telemetria que segue continuamente um veículo em movimento a partir do
GPS que ele mesmo transmite — o mesmo princípio de uma estação terrena de
satélite, com a mesma geodesia WGS84 —, não uma reprodução do protocolo
Geo-Pointing/GPM da FLIR.

Por isso o simulador continua implementando essa funcionalidade sob um
conjunto de comandos **claramente identificado como extensão própria**,
por cima do protocolo serial ASCII já usado no resto do simulador (por
simplicidade de integração, já que o objetivo aqui é ensinar o conceito
de rastreamento de antena, não replicar byte a byte um recurso Ethernet
que teria de ser modelado como um serviço à parte):

| Comando | | Descrição |
|---------|--|-----------|
| `GO<lat>,<lon>,<alt>` | 🔧 | Define a posição da **estação de solo** (observador). Sem valor, consulta. |
| `GX<lat>,<lon>,<alt>` | 🔧 | Define a posição do **alvo** (veículo rastreado). Sem valor, consulta. Se o rastreamento estiver habilitado (`GE`), o pan-tilt já se move para o novo apontamento. |
| `GE` | 🔧 | Habilita o rastreamento automático: cada `GX` recalcula azimute/elevação e comanda `PP`/`TP`. |
| `GD` | 🔧 | Desabilita o rastreamento automático (posição atual não muda). |
| `GA` | 🔧 | Consulta os últimos ângulos calculados: `azimute,elevação,distância`. |

🔧 = extensão própria deste simulador — funcionalidade real, sintaxe não
confirmada contra o manual oficial.

Latitude/longitude são graus decimais WGS84 (o mesmo datum que o GPS usa
nativamente); altitude é elipsoidal, em metros. O cálculo é geodésico →
ECEF (Earth-Centered, Earth-Fixed) → ENU (East-North-Up, plano tangente
local da estação) — o método padrão de rastreamento de antena, não uma
aproximação de Terra plana; ver `pantiltsim/tracking.py` para a
implementação e `tests/test_tracking.py` para os casos de referência
conferidos à mão.

**Isto não é orientação de armas.** O módulo só resolve "para onde
apontar" a partir de duas posições geográficas — a mesma matemática vale
para qualquer veículo com GPS. Ele não rastreia, identifica nem interage
com o veículo: apenas converte coordenadas recebidas de uma fonte externa
(um receptor GPS real, ou aqui, para demonstração, o gerador de
trajetória `LinearTrajectory`) num ângulo de apontamento de antena — a
mesma função que uma antena parabólica de estação terrena exerce ao
seguir um satélite.

Se você precisar do comportamento **oficial** do Geo-Pointing/GPM da FLIR
byte a byte (interface Ethernet/IP, fluxo de calibração por landmarks),
isso está fora do escopo desta extensão serial — seria um serviço/porta
separado a implementar à parte, não um ajuste de nomenclatura em cima do
que já existe aqui.

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
serial ASCII (PP/TP e o restante da tabela deste documento):

- <https://github.com/hmorris94/FLIR-PTU-Python> — `flirptu/ptu.py`
- <https://github.com/cburbridge/flir_pantilt_d46> — `src/ptu46_driver.cc`
- <https://github.com/usc-clmc/usc-arm-calibration> —
  `arm_head_control/flir_cpi/code/ptu.c` (terceiro driver independente;
  confirma o mesmo conjunto de comandos serial P/T e **não contém nenhum
  comando de geo-posicionamento** — reforça que o Geo-Pointing não faz
  parte do protocolo serial)

Fontes sobre o **Geo-Pointing (GPM)** real, acessadas via trechos
indexados de busca (o texto completo das páginas continua bloqueado, mas
os resultados de busca trazem excertos das páginas oficiais da FLIR o
suficiente para confirmar os fatos usados na seção "Rastreamento de
antena por GPS" acima):

- `flir.custhelp.com/app/answers/detail/a_id/3233` — "PTU Geo-Pointing
  Functionality"
- `flir.custhelp.com/app/answers/detail/a_id/3393` — "GPM and ISM, GPM
  accuracy"
- `flir.custhelp.com/app/answers/detail/a_id/3146` — "PTU Pan Tilt System
  For Antennas"
- `sustainable-robotics.com/reference/PTU/GPM1.0/PTU-manual-DGPM-V1.0.pdf`
  — "Web Enabled Geo-Pointing Module Model PTU-DGPM USER'S MANUAL Version
  1.0" (localizado, mas não acessado — mesmo bloqueio de rede)
