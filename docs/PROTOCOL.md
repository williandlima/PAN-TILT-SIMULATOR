# Protocolo implementado (DPCL — Pan-Tilt Command Language)

O PTU-D300E (fabricante Teledyne FLIR / Directed Perception, linha
"E-Series" — que também inclui PTU-D46, PTU-D48E, PTU-D100E) é controlado
por um conjunto de comandos ASCII conhecido informalmente como **DPCL**
(Directed Perception / Pan-Tilt Command Language). Esse é o mesmo
protocolo, com o mesmo conjunto básico de comandos, usado em toda a
família de pan-tilts desde o PTU-D46 até o D300E — daí ser possível
validar a estrutura do protocolo mesmo sem acesso direto ao PDF oficial
do D300E.

## Fontes consultadas

Durante o desenvolvimento, tentou-se buscar o *Command Reference Manual*
oficial da FLIR para conferir byte a byte cada resposta. A política de
rede desta sessão bloqueou o acesso aos seguintes domínios (todos
encontrados via busca, mas inacessíveis a partir daqui):

- `movitherm.com` (hospeda `PTU-D300E-Manual.pdf` e
  `E-Series-Command-Reference-Manual.pdf`)
- `sustainable-robotics.com` (hospeda cópias dos mesmos manuais)
- `flir.netx.net`, `oem.flir.com`, `tekgear.com`, `manualslib.com`,
  `adept.net.au`, `cs.unc.edu`

**Recomenda-se obter esses PDFs manualmente** (a busca web confirmou que
existem publicamente nesses endereços) e comparar com `protocol.py` caso
seja necessário fidelidade absoluta ao firmware real do seu PTU-D300E.

O que **foi** possível confirmar com uma fonte acessível e verificável
(código-fonte real, não um resumo de terceiros) foi o driver de código
aberto do ROS `flir_pantilt_d46` (`cburbridge/flir_pantilt_d46`, arquivo
`src/ptu46_driver.cc`), que se comunica com hardware PTU-D46 real. Dele
foram extraídos, lendo o código diretamente:

- Formato de comando de eixo: `"%cp%d "` / `"%cs%d "` com `%c` = `'p'`
  (pan) ou `'t'` (tilt) — ou seja, comando = `<eixo><código><valor><espaço>`,
  ex.: `"pp1000 "` (equivalente, case-insensitive, a `"PP1000 "`).
- Formato de resposta numérica: `"*p1500"` — asterisco, letra do eixo
  em minúsculo, valor, sem separador. Confirmado lendo o parsing real:
  `buffer[0] == '*'` e `strtod(&buffer[2], NULL)`.
- Sequência de inicialização usada pelo driver: `" r "` (reset), depois
  espera a resposta `"!T!T!P!P*"`; em seguida `"ft "` (feedback terse),
  `"ed "` (echo disable), `"ci "` (modo posição).
- Caracteres de tipo/eixo: `'p'` (pan), `'t'` (tilt) e códigos de
  comando `'n'`/`'x'` (limite mín/máx), `'l'`/`'u'` (limite de
  velocidade inferior/superior), `'v'`/`'i'` (modo velocidade/posição).

Essa evidência bate exatamente com a nomenclatura de comandos
publicamente documentada para a "Pan-Tilt Command Language" (PP, TP, PS,
TS, PA, TA, PN, PX, TN, TX, PU, TU, PL, TL, CI, CV, FT, FV, ED, EE, R),
então o simulador implementa esse conjunto completo.

## Formato geral

```
<comando> ::= <comando-de-eixo> | <comando-global>

<comando-de-eixo>   ::= <eixo><código>[valor] <terminador>
<eixo>              ::= "P" | "T"   (case-insensitive)

<comando-global>    ::= <código>[valor] <terminador>
<terminador>        ::= espaço, CR ou LF (qualquer um funciona)
```

- Omitir o valor faz o comando virar uma **consulta** (query), que
  retorna o valor atual daquele parâmetro.
- Vários comandos podem ser enviados em uma única linha, separados por
  espaço: `"PA3000 TA3000 PS800 TS800 "`.
- Respostas de sucesso começam com `*`; erros começam com `!`.
- Se o eco estiver habilitado (`EE`, padrão de fábrica), cada comando
  recebido é ecoado de volta antes da resposta.

## Comandos de eixo (prefixo `P`=pan ou `T`=tilt)

| Comando | Descrição                                   | Exemplo         | Consulta |
|---------|----------------------------------------------|-----------------|----------|
| `PP`/`TP` | Posição desejada (absoluta, em contagens)   | `PP1000 `       | `PP `    |
| `PO`/`TO` | Deslocamento relativo (offset) de posição   | `PO500 `        | `PO ` (sempre retorna 0, não persiste) |
| `PS`/`TS` | Velocidade desejada (contagens/s)           | `PS1500 `       | `PS `    |
| `PA`/`TA` | Aceleração desejada (contagens/s²)          | `PA3000 `       | `PA `    |
| `PB`/`TB` | Velocidade base (rampa)                     | `PB500 `        | `PB `    |
| `PU`/`TU` | Limite superior de velocidade               | `PU6000 `       | `PU `    |
| `PL`/`TL` | Limite inferior de velocidade               | `PL0 `          | `PL `    |
| `PN`/`TN` | Limite mínimo de posição (curso)            | `PN-15900 `     | `PN `    |
| `PX`/`TX` | Limite máximo de posição (curso)            | `PX15900 `      | `PX `    |
| `PH`/`TH` | Halt (para) apenas este eixo                | `PH `           | —        |

Resposta de consulta (modo terso, padrão): `*p1500\r\n` (posição de pan =
1500 contagens). Resposta de comando de ajuste: `*\r\n` (terso) ou
`* OK <descrição>\r\n` (verboso, ver `FV`).

## Comandos globais

| Comando | Descrição                                          |
|---------|-----------------------------------------------------|
| `H`     | Halt geral (para pan e tilt imediatamente)           |
| `A`     | Aguarda a conclusão do movimento em curso antes de responder |
| `I`     | Modo de execução imediato (padrão)                   |
| `S`     | Modo de execução "slaved" (registrado; ver limitações)|
| `R`     | Reset — restaura parâmetros de fábrica. Resposta fixa: `!T!T!P!P*` (confirmado no driver de referência) |
| `V`     | Consulta a versão de firmware simulada                |
| `CI`    | Modo de controle = Posição                            |
| `CV`    | Modo de controle = Velocidade contínua                |
| `FT`    | Feedback terso (respostas curtas, `*...`)              |
| `FV`    | Feedback verboso (respostas descritivas)               |
| `ED`    | Desabilita eco de comandos                             |
| `EE`    | Habilita eco de comandos                                |
| `LE`    | Habilita limites de curso (pan e tilt)                  |
| `LD`    | Desabilita limites de curso (pan e tilt)                |
| `DF`    | Restaura configurações de fábrica (equivalente a reset) |
| `DS`    | Salva configurações atuais como padrão                  |
| `DR`    | Restaura últimas configurações salvas com `DS`          |

## Modo velocidade contínua (`CV`)

Quando o modo de controle é `CV`, os comandos `PS`/`TS` passam a definir
uma **velocidade contínua** (com sinal) em vez de uma velocidade máxima
para um movimento até uma posição-alvo — o eixo se move continuamente
naquele sentido até receber `H`/`PH`/`TH` ou até atingir um limite de
curso (se `LE` estiver ativo). Isso corresponde ao comportamento
documentado de "Velocity Move Mode" da família DPCL.

## Erros

Respostas de erro seguem o formato `!<código> <mensagem>\r\n`, por
exemplo:

```
!1 Unknown command 'ZZ'
!2 Invalid integer value 'abc'
```

Esse formato (prefixo `!`) foi escolhido por consistência com a única
resposta de erro/status confirmada no hardware real (`!T!T!P!P*` do
comando de reset), mas os textos das mensagens são uma convenção deste
simulador — ajuste-os em `pantiltsim/protocol.py` se precisar bater
exatamente com mensagens do firmware real.

## Limitações conhecidas / simplificações

- O modo "Slaved" (`S`/`I`) é registrado no estado do dispositivo mas o
  simulador executa todo comando de posição imediatamente — não há uma
  fila de movimentos sincronizados aguardando um `A` global antes de
  disparar pan e tilt juntos.
- `LE`/`LD` neste simulador afetam pan e tilt simultaneamente (não há
  comando separado por eixo); no firmware real pode haver variações.
- Os valores padrão de resolução (contagens/grau), curso e velocidade
  máxima em `pantiltsim/device.py` (`AxisConfig`) são parâmetros
  **configuráveis**, não os valores exatos de fábrica do seu PTU-D300E
  específico (que variam conforme a opção de gear ratio/encoder do
  pedido) — ajuste conforme a etiqueta/datasheet do seu equipamento.
- Não foi implementado o subconjunto binário do protocolo nem Pelco-D
  (mencionados na documentação da FLIR como protocolos alternativos
  suportados pela unidade) — apenas o protocolo ASCII, que é o padrão
  para controle via RS-232/RS-485/USB.
