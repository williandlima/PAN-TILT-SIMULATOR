# Guia do operador — Simulador PTU-D300E

Este guia é para quem vai **usar** o simulador sem precisar entender o
código por trás dele: o que cada tela faz, o que cada termo técnico
significa em português simples, e como funcionam os modos de teste. Não
é preciso saber programar para acompanhar este documento.

Se você quiser o lado técnico/protocolo completo, ele está em
[`PROTOCOL.md`](PROTOCOL.md); o passo a passo de instalação está em
[`PROCEDIMENTO.md`](PROCEDIMENTO.md). Este guia aqui é só sobre **usar**
o programa já instalado.

---

## 1. O que é este programa, em uma frase

É um **imitador de hardware**: um programa de computador que se comporta
exatamente como um pan-tilt (uma base motorizada que gira uma câmera,
antena ou sensor em duas direções) de verdade, respondendo aos mesmos
comandos que o equipamento físico responderia. Serve para treinar,
testar software e demonstrar o funcionamento **sem precisar ter o
equipamento real na bancada**.

Pense nele como um "simulador de voo", só que de uma base giratória de
câmera/antena em vez de um avião.

---

## 2. A única ideia que você precisa entender primeiro

O equipamento (e o simulador) **não pensa em graus** — ele pensa em
**contagens** (também chamadas de "counts"). Uma contagem é a menor
unidade de movimento que o motor consegue dar, tipo um "degrau" bem
pequeno de giro. Quantos graus vale uma contagem depende do modelo e da
configuração da engrenagem interna.

Você não precisa fazer essa conta na mão: a interface gráfica (a tela
com botões) já mostra e recebe tudo em **graus** — é só quem for digitar
comandos crus no terminal, ou programar um software cliente, que
precisa se preocupar com contagens. Guarde só isto: *"contagem" é a
unidade que a máquina usa por dentro; "grau" é o que você vê na tela.*

---

## 3. Abrindo o simulador

No terminal (prompt de comando):

```bash
ptu-sim --gui
```

Isso abre a janela do simulador. Ele já nasce **funcionando sozinho**,
sem precisar ligar nenhum cabo — a base "virtual" já está de pé em 0°/0°
e responde a tudo que você clicar. A porta serial (USB ou RS-485) só é
necessária quando **outro programa** (o software que você está testando,
por exemplo) precisa comandar o simulador de fora.

---

## 4. Tour pela tela

### Faixa superior

O cabeçalho azul-marinho com a logo mostra qual modelo está sendo
simulado (ex.: PTU-D300E).

### O desenho 3D (lado esquerdo)

Mostra a base giratória em 3D, em tempo real: gira e inclina exatamente
como o equipamento faria. Embaixo dele, dois "relógios": um mostra o
giro horizontal (pan) e outro o giro vertical (tilt), como uma bússola.

### "Conexão (RS-485 / USB)"

É aqui que você liga o simulador a uma porta serial de verdade — só
necessário se outro programa/computador for comandar o simulador de
fora. Se você só quer testar clicando na própria tela, pode ignorar esta
caixa completamente.

- **Porta**: qual porta COM (Windows) ou `/dev/tty...` (Linux) usar.
  Clique em **Atualizar** para a lista recarregar.
- **Interface**: se a ligação física é **USB** (a mais comum) ou
  **RS-485** (um tipo de fiação industrial que permite cabos mais
  longos, mas exige um adaptador específico).
- O número ao lado (ex.: 9600) é a **velocidade da porta** (baud rate) —
  quantos "sinais" por segundo trafegam no cabo. Os dois lados (simulador
  e programa cliente) precisam estar na mesma velocidade, senão não se
  entendem — é como duas pessoas tentando conversar em velocidades de
  fala completamente diferentes.
- **Reconectar automaticamente**: se o cabo cair ou o adaptador USB for
  desconectado sem querer, o simulador tenta reabrir a porta sozinho.

### "Telemetria do PTU"

Mostra o estado atual: posição de giro (em graus **e** em contagens),
quão fino é o movimento (resolução), até onde ele pode girar (curso),
velocidade no momento, e os modos ativos.

### Aba "Controle"

Onde você manda a base se mexer:

- **Pan alvo / Tilt alvo**: para onde você quer que ela aponte (em
  graus). Pan = giro horizontal (esquerda-direita); Tilt = giro vertical
  (cima-baixo).
- **Velocidade**: quão rápido ela gira até chegar lá (graus por
  segundo).
- **Passo do jog**: o quanto cada clique nas setas move a base.
- **Ir para posição**: manda a base girar até o Pan/Tilt alvo escolhido.
- As setas (◄ ► ▲ ▼) e o botão **Centro** movem aos poucos ou voltam
  para 0°/0°.
- **Halt**: para tudo na hora, mesmo no meio de um movimento. **Halt
  pan**/**Halt tilt** param só um dos dois eixos.
- **Reset**: volta ao estado de fábrica (zera posição e todas as
  configurações).
- **Aguardar**: um botão mais usado por programadores — trava a
  interface até o movimento em curso terminar (serve para testar como
  um software cliente reagiria a essa espera).
- **Modo monitor / auto-scan**: liga uma varredura automática — a base
  fica indo de um lado a outro sozinha, sem parar, entre os limites de
  curso. Bom para deixar rodando e observar de longe.

### Aba "Configuração"

Ajustes de comportamento, não de posição:

- **Modo de controle**: *Posição* (você diz "vá para X graus") ou
  *Velocidade* (você diz "gire continuamente a X graus/segundo" até
  mandar parar).
- **Limites de curso**: até onde a base pode ir. *Fábrica* = os limites
  de segurança do equipamento; *Usuário* = limites mais apertados que
  você mesmo define; *Desabilitado* = sem limite nenhum (cuidado).
- **Micropasso**: o quão "fino" é cada contagem de movimento — quanto
  mais fino (ex.: "Eighth"/oitavo de passo), mais suave e preciso o
  movimento, mas a mesma distância em graus passa a valer mais
  contagens.
- **Potência parado / potência movendo**: o quanto de força o motor
  aplica quando está parado segurando a posição, e quando está
  girando — mais potência segura mais firme e vence mais peso, mas
  esquenta/gasta mais energia.
- **Eco de comandos**: se o equipamento "repete de volta" cada comando
  recebido antes de responder — útil para quem está depurando um
  software cliente.
- **Feedback verboso**: se as respostas vêm com frase explicativa
  ("A posição atual do Pan é 1000") ou só o número seco ("1000"). Um
  software de verdade normalmente prefere a resposta seca (mais rápida
  de processar); um humano lendo prefere a frase.
- **Execução slaved**: um modo onde pan e tilt só começam a se mover
  juntos, ao mesmo tempo, quando você manda um comando de "agora vale"
  — em vez de cada um sair andando assim que é comandado.

### Aba "Rastreamento GPS"

Ver a seção 6 deste guia — é o recurso mais avançado do simulador.

### Aba "Terminal DPCL"

Uma caixa de texto onde você digita comandos "crus" do protocolo do
fabricante (ex.: `PP1000`) e vê a resposta exata que o equipamento real
daria. É como conversar diretamente com a "língua" que o equipamento
fala, sem passar pelos botões da interface. Digite **`?`** para uma
lista rápida de comandos, ou **`??`** para abrir esta mesma ajuda
completa.

---

## 5. Glossário — todo termo técnico traduzido

### Sobre o movimento

| Termo | O que significa |
|---|---|
| **Pan** | Giro horizontal — esquerda e direita, como balançar a cabeça dizendo "não". |
| **Tilt** | Giro vertical — cima e baixo, como balançar a cabeça dizendo "sim". |
| **Contagem** (*count*) | A menor unidade de movimento do motor — um "degrauzinho" de giro. É a unidade que a máquina usa por dentro. |
| **Resolução** | Quantos segundos de arco (uma fração minúscula de grau) cada contagem representa. Quanto menor esse número, mais fino o movimento. |
| **Curso** | O intervalo de ângulos que o eixo pode alcançar (ex.: de -159° a +159° no pan). |
| **Micropasso** (*step mode*) | O nível de "fatiamento fino" do movimento do motor — Full, Half, Quarter, Eighth (inteiro, meio, um quarto, um oitavo de passo) ou Auto. |
| **Velocidade alvo/instantânea** | Velocidade *alvo* é a que você pediu; *instantânea* é a que o eixo está de fato girando naquele exato momento (durante a aceleração, por exemplo, ainda não chegou na velocidade pedida). |
| **Aceleração** | Quão rápido a velocidade sobe até chegar na velocidade alvo — como o "afundar o acelerador" de um carro, mas para o motor do pan-tilt. |
| **Perfil trapezoidal** | O jeito como o movimento acontece de verdade: acelera, mantém a velocidade de cruzeiro, e desacelera ao chegar perto do alvo — não "teletransporta" para a posição. |
| **Halt** | Parar imediatamente, onde estiver. |
| **Jog** | Mover aos poucos, passo a passo, clicando em setas — em vez de digitar um ângulo exato. |
| **Modo monitor / auto-scan** | Varredura automática contínua entre os limites de curso, sem precisar clicar de novo. |

### Sobre a comunicação (o "fio")

| Termo | O que significa |
|---|---|
| **RS-485** | Um padrão de fiação industrial que permite cabos mais longos e vários equipamentos na mesma linha — precisa de um adaptador específico. |
| **USB** | A porta serial mais comum; o próprio equipamento aparece como uma "porta COM" no computador quando ligado por USB. |
| **Baud rate** | A velocidade da comunicação pela porta serial — os dois lados (equipamento e programa) precisam usar o mesmo número. |
| **Porta serial / porta COM** | O "canal" de comunicação entre o computador e o equipamento — no Windows aparece como `COM3`, `COM4`...; no Linux, como `/dev/ttyUSB0`, por exemplo. |
| **Protocolo** | O conjunto de regras/"vocabulário" que os dois lados usam para se entender — aqui, o protocolo é o **DPCL**. |
| **DPCL** | O nome do "idioma" (protocolo ASCII) que o equipamento fala — sigla de *Pan-Tilt Command Language*, a linguagem de comandos do fabricante. |
| **Eco** | O equipamento "repetir de volta" o comando recebido antes de responder — como uma pessoa repetir "ok, 45 graus" antes de fazer o que foi pedido. |
| **Modo terso / verboso** | *Terso* = resposta curta, só o número (`* 1000`); *verboso* = resposta com frase explicando (`* A posição atual é 1000`). |
| **Await (Aguardar)** | Um comando que "segura a linha" — só responde quando o movimento em curso terminar, em vez de responder na hora e deixar o movimento continuar em paralelo. |

### Sobre o protocolo e a configuração

| Termo | O que significa |
|---|---|
| **Comando** | Uma instrução enviada ao equipamento, sempre em texto (ex.: `PP1000` = "pan, ir para a posição 1000"). |
| **Consulta** | Um comando sem valor, que só pergunta o estado atual (ex.: `PP` sozinho pergunta "qual é a posição do pan agora?"). |
| **Resposta de sucesso / erro** | Toda resposta que começa com `*` deu certo; toda que começa com `!` é um erro. |
| **Slaved** | Modo em que os comandos de pan e tilt ficam "engatilhados" e só disparam juntos quando um comando de "vai" chega — para os dois eixos partirem exatamente ao mesmo tempo. |
| **Limites de curso: fábrica / usuário / desabilitado** | *Fábrica* = limites de segurança do equipamento; *Usuário* = limites mais apertados definidos por quem está operando; *Desabilitado* = sem limite (risco de tentar ir além do fisicamente possível). |
| **Potência: parado / movendo** | Quanta força o motor aplica quando está segurando a posição parado, versus quando está de fato girando. |
| **Reset** | Volta tudo ao estado de fábrica — posição zerada e configurações padrão. |

### Sobre o rastreamento GPS (Geo Pointing Module)

| Termo | O que significa |
|---|---|
| **GPM (Geo Pointing Module)** | O recurso, embutido no próprio equipamento, de apontar usando coordenadas geográficas (latitude/longitude/altitude) em vez de graus relativos. |
| **Latitude / Longitude / Altitude** | As três coordenadas que localizam qualquer ponto no planeta — as mesmas que um GPS de celular mostra. |
| **Posição própria da unidade** | Onde a base está fisicamente instalada no mundo — precisa ser informada para o cálculo de apontamento funcionar. |
| **Azimute** | Para que direção apontar, na horizontal, medido a partir do norte (0° = norte, 90° = leste, 180° = sul, 270° = oeste). |
| **Elevação** | O quanto apontar para cima ou para baixo, em graus, a partir da linha do horizonte (0° = horizonte, 90° = reto para cima). |
| **Aim point** (ponto de mira) | A coordenada geográfica para onde a base foi mandada apontar agora. |
| **Landmark** | Um ponto de referência de posição conhecida, salvo para ajudar a calibrar a instalação da unidade. |
| **Telemetria** | Os dados que um veículo (avião, drone, foguete de teste) transmite por rádio sobre si mesmo em tempo real — incluindo sua própria posição de GPS. |
| **Rastreamento de antena** | Uma antena em terra que gira continuamente para acompanhar um veículo em movimento, de olho na posição que ele mesmo está transmitindo — para não perder o sinal de rádio. **Não é** guiar o veículo a lugar nenhum; é só "ficar de olho" para continuar recebendo os dados dele. |
| **Predição por velocidade** (*rate-aided tracking*) | Estimar para onde o alvo está indo (pela velocidade dele) e apontar um pouco à frente, para compensar o tempo que a informação leva para chegar e o pedestal girar. |

---

## 6. O rastreamento GPS, em linguagem simples

A aba "Rastreamento GPS" tem duas partes:

1. **Posição própria da unidade**: você informa onde a base está
   instalada (latitude, longitude, altitude) e clica em **Definir
   posição**. Isso é um comando real do equipamento (chamado `GLLA` no
   protocolo).
2. **Alvo**: você informa a posição de algo que quer que a base
   aponte (um avião, drone, ou qualquer ponto do mapa) e clica em
   **Apontar**. A base calcula sozinha para que direção e inclinação
   girar, e vai até lá. Isso também é um comando real (`GG`).

Para simular um veículo *em movimento* (em vez de um ponto parado), use
a caixinha **"Trajetória de demonstração"**: escolha rumo, velocidade e
taxa de subida, clique em **Iniciar demonstração**, e o simulador vai
"fingir" ser um avião voando em linha reta, atualizando a posição do
alvo várias vezes por segundo — e a base vai seguindo sozinha.

A caixa **"Predição por velocidade"** deixa a base apontar um pouco à
frente de onde o alvo foi visto por último, em vez de sempre correndo
atrás — é o mesmo truque que uma estação de rastreamento de verdade usa
para compensar o tempo que a informação leva para chegar e o motor
girar. Comece com 0 (desligado) e só aumente se quiser ver esse efeito.

**Importante**: isto não é um sistema de guiagem de armas nem de
mira militar. É a mesma tecnologia usada para uma antena de estação
terrena seguir um satélite, ou uma estação de telemetria acompanhar um
foguete de teste — a base só sabe apontar para onde uma posição de GPS
(a do próprio alvo, transmitida por ele mesmo) diz que ele está. Ela não
identifica, não decide e não interage com nada sozinha.

---

## 7. Os modos de teste, explicados

Existem várias formas de "colocar o simulador para trabalhar",
dependendo do que você quer verificar. Do mais simples ao mais parecido
com o uso real:

### 1. Modo local — sem nenhum cabo

É como o programa abre por padrão. Você mexe pelos botões da própria
tela e vê o resultado na hora — nenhuma porta serial precisa estar
ligada. Serve para conhecer o comportamento do equipamento e fazer
demonstrações, sem fiação nenhuma.

### 2. Loopback — duas "portas de mentira" ligadas uma na outra

Para testar o **seu próprio programa** (o software que vai comandar o
equipamento de verdade) contra o simulador, sem precisar de nenhum
cabo físico. Cria-se um par de portas seriais virtuais dentro do
próprio computador, liga-se o simulador numa ponta e o seu programa na
outra — é como se fossem dois computadores ligados por um cabo, só que
tudo dentro da mesma máquina.

### 3. Fiação real — RS-485 ou USB de verdade

O simulador roda num computador (ou numa placa como a BeagleBone) e é
comandado por outro equipamento real através de um cabo de verdade —
exatamente como aconteceria com o pan-tilt físico. Serve para validar
que a fiação, os adaptadores e as velocidades de porta estão certos
antes de usar o equipamento real.

### 4. Autoteste de aceitação — um botão só

Um comando único que liga o simulador de um lado de um par de portas
virtuais e, do outro, roda uma sequência automática que imita o que um
controlador de verdade faria (perguntar a resolução, mover, esperar
terminar, mover os dois eixos juntos, parar, testar limites) —
imprimindo **PASSOU** ou **FALHOU** no final. Serve para conferir
rapidinho, sem precisar clicar em nada, que está tudo funcionando.

### 5. Suíte automatizada de testes

Uma bateria bem maior de verificações automáticas (mais de 80),
pensada para quem está desenvolvendo ou alterando o próprio simulador —
confere cada comando, cada resposta, e até um teste que liga tudo numa
porta serial real do sistema operacional. Um operador do dia a dia não
precisa rodar isto; é mais para quem mantém o software.

---

## 8. Problemas comuns

| O que você vê | O que provavelmente é |
|---|---|
| A lista de portas está vazia | Nenhum dispositivo serial (cabo USB, adaptador RS-485) está conectado ao computador, ou o driver dele não está instalado. Clique em **Atualizar** depois de conectar. |
| Cliquei em Conectar e deu erro | A porta pode já estar sendo usada por outro programa, ou você escolheu uma porta que não existe/não é a certa. |
| A base não se move | Confira se um limite de curso está bloqueando (aba Configuração), ou se está em "Modo monitor" (que assume o controle sozinho). |
| A resposta no terminal parece estranha/cortada | Confira se **Feedback verboso** e **Eco** estão no que você espera — eles mudam bastante o formato da resposta. |
| O rastreamento GPS não aponta para lugar nenhum | Confira se você já clicou em **Definir posição (GLLA)** para a posição própria da unidade — sem isso, o cálculo não tem de onde partir. |

---

## 9. Onde buscar mais ajuda

- Dentro do próprio programa: menu **Ajuda**, ou teclas **F1** (primeiros
  passos), **F2** (modos de teste), **F3** (lista de comandos), **F4**
  (rastreamento GPS).
- No terminal da aba "Terminal DPCL": digite **`?`** para um resumo
  rápido, ou **`??`** para abrir esta mesma ajuda completa.
- Para o detalhamento técnico do protocolo (para quem for programar um
  software cliente): [`PROTOCOL.md`](PROTOCOL.md).
- Para instalar, testar e configurar o simulador do zero:
  [`PROCEDIMENTO.md`](PROCEDIMENTO.md).
