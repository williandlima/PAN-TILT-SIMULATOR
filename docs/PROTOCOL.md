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
conferência):

- `movitherm.com` — `PTU-D300E-Manual.pdf`, `E-Series-Command-Reference-Manual.pdf`
- `sustainable-robotics.com` — cópias dos mesmos manuais
- `flir.netx.net`, `oem.flir.com`, `tekgear.com`, `manualslib.com`,
  `adept.net.au`, `cs.unc.edu`

Fontes efetivamente acessadas e usadas para verificação:

- <https://github.com/hmorris94/FLIR-PTU-Python> — `flirptu/ptu.py`
- <https://github.com/cburbridge/flir_pantilt_d46> — `src/ptu46_driver.cc`
