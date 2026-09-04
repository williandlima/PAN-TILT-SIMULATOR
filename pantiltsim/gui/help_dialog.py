"""Ajuda embutida no simulador.

Ensina o software a partir do núcleo do projeto: a unidade nativa do
protocolo do fabricante são *contagens*, e é o comando ``PR``/``TR`` que
diz quantas contagens valem um grau. Quem entende isso usa o simulador
(e o equipamento real) sem tropeçar; quem não entende fica convertendo
ângulo no chute.

O conteúdo é gerado a partir do dispositivo em uso, então os números que
aparecem na ajuda (resolução, curso, contagens por grau) são os da
configuração carregada — e não valores fixos que podem mentir quando o
usuário roda com ``--config``.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QListWidget,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
)

from ..device import PanTiltDevice

_CSS = """
<style>
  body { font-family: sans-serif; font-size: 10.5pt; line-height: 1.5; }
  h2 { font-size: 13pt; margin: 0 0 6px 0; }
  h3 { font-size: 11pt; margin: 16px 0 4px 0; }
  p, li { margin: 0 0 8px 0; }
  code { font-family: monospace; background: rgba(128,128,128,0.16);
         padding: 1px 4px; border-radius: 2px; }
  pre { font-family: monospace; background: rgba(128,128,128,0.13);
        padding: 8px 10px; margin: 6px 0 12px 0; }
  table { border-collapse: collapse; margin: 4px 0 12px 0; width: 100%; }
  th { text-align: left; padding: 4px 10px 4px 0; font-size: 9pt;
       text-transform: uppercase; }
  td { padding: 3px 10px 3px 0; vertical-align: top; }
  .lead { color: #888; }
</style>
"""


def _quick_start(device: PanTiltDevice) -> str:
    pan_counts_45 = device.pan.deg_to_counts(45.0)
    tilt_counts_20 = device.tilt.deg_to_counts(20.0)
    return f"""
    <h2>Primeiros passos</h2>
    <p class="lead">Do zero até ver o pan-tilt se mexendo, em um minuto.</p>

    <h3>1. Mover pela interface</h3>
    <p>
      Na aba <b>Controle</b>, escreva <code>45</code> em <i>Pan alvo</i>,
      <code>20</code> em <i>Tilt alvo</i> e clique em
      <b>Ir para posição</b>. A unidade gira até lá, a bússola e o arco de
      tilt acompanham, e o rótulo muda de <b>EM MOVIMENTO</b> para
      <b>EM POSIÇÃO</b>.
    </p>
    <p>
      Isso funciona <b>sem conectar porta nenhuma</b>: o simulador começa em
      modo local. A porta serial só é necessária quando outro programa for
      comandar o simulador.
    </p>

    <h3>2. Ver o comando por trás do botão</h3>
    <p>
      Abra a aba <b>Terminal DPCL</b>: cada clique da interface aparece ali
      como o comando ASCII que seria enviado pela porta serial. O botão que
      você acabou de usar mandou algo como:
    </p>
    <pre>PS{device.pan.deg_to_counts(20.0)} TS{device.tilt.deg_to_counts(20.0)} PP{pan_counts_45} TP{tilt_counts_20}</pre>
    <table>
      <tr><th>Trecho</th><th>Significa</th></tr>
      <tr><td><code>PS{device.pan.deg_to_counts(20.0)}</code></td><td>velocidade de pan: 20 °/s</td></tr>
      <tr><td><code>TS{device.tilt.deg_to_counts(20.0)}</code></td><td>velocidade de tilt: 20 °/s</td></tr>
      <tr><td><code>PP{pan_counts_45}</code></td><td>pan para 45°</td></tr>
      <tr><td><code>TP{tilt_counts_20}</code></td><td>tilt para 20°</td></tr>
    </table>
    <p>
      Repare que os quatro números estão em <b>contagens</b>, não em graus — é
      assim que o equipamento fala. A próxima página explica a conversão.
    </p>
    <p>
      Não existe caminho "de fora" e caminho "de dentro": a interface fala o
      mesmo protocolo que um controlador externo falaria.
    </p>

    <h3>3. Digitar um comando</h3>
    <p>
      No campo do terminal, digite <code>PR</code> e tecle Enter — é a
      consulta de resolução. Depois experimente <code>PP{pan_counts_45}</code>,
      e veja a unidade se mover. Digite <code>?</code> para a lista de
      comandos.
    </p>

    <h3>4. Parar</h3>
    <p>
      <code>H</code> (ou o botão <b>Halt</b>) para os dois eixos na hora.
      <code>HP</code> e <code>HT</code> param só o pan ou só o tilt.
    </p>
    """


def _core_concepts(device: PanTiltDevice) -> str:
    pan = device.pan
    tilt = device.tilt
    return f"""
    <h2>O núcleo: contagens, não graus</h2>
    <p class="lead">
      O conceito que evita 90% dos erros ao integrar com o equipamento.
    </p>

    <p>
      O protocolo do fabricante <b>não trabalha em graus</b>. Toda posição e
      toda velocidade são expressas em <b>contagens</b> (posições de encoder).
      Quantos graus vale uma contagem depende da redução, do encoder e do
      modo de micropasso — por isso o equipamento tem um comando só para
      informar isso: <code>PR</code> (pan) e <code>TR</code> (tilt), que
      devolvem a resolução em <b>segundos de arco por contagem</b>.
    </p>

    <p>A conta que todo driver faz ao abrir a conexão:</p>
    <pre>contagens_por_grau = 3600 / resolução</pre>

    <h3>Nesta configuração agora</h3>
    <table>
      <tr><th>Eixo</th><th>Resolução</th><th>Contagens/grau</th><th>Curso</th></tr>
      <tr>
        <td>Pan</td>
        <td>{pan.arcsec_per_count:.4f} ″/cont.</td>
        <td>{pan.counts_per_degree:.2f}</td>
        <td>{pan.counts_to_deg(pan.effective_min):.1f}° a {pan.counts_to_deg(pan.effective_max):.1f}°</td>
      </tr>
      <tr>
        <td>Tilt</td>
        <td>{tilt.arcsec_per_count:.4f} ″/cont.</td>
        <td>{tilt.counts_per_degree:.2f}</td>
        <td>{tilt.counts_to_deg(tilt.effective_min):.1f}° a {tilt.counts_to_deg(tilt.effective_max):.1f}°</td>
      </tr>
    </table>
    <p>
      Ou seja: 45° de pan são <b>{pan.deg_to_counts(45.0)} contagens</b>, e o
      comando fica <code>PP{pan.deg_to_counts(45.0)}</code>. Nunca escreva
      esse número fixo no seu código — pergunte com <code>PR</code>, porque
      ele muda com o micropasso e com o modelo da unidade.
    </p>

    <h3>Por que o micropasso muda tudo</h3>
    <p>
      Trocar o micropasso (<code>WPF</code>, <code>WPQ</code>, …) muda a
      resolução e, com ela, o significado das contagens. O simulador reescala
      as contagens preservando o <b>ângulo físico</b> — igual ao hardware. Se
      o seu programa guardou "45° = {pan.deg_to_counts(45.0)} contagens" e o
      micropasso mudou, esse número passa a apontar para outro ângulo.
      Releia <code>PR</code> depois de qualquer troca.
    </p>

    <h3>O movimento é físico, não instantâneo</h3>
    <p>
      Um <code>PP</code> não teletransporta o eixo: ele acelera, atinge a
      velocidade de <code>PS</code> e desacelera (perfil trapezoidal), com os
      limites de curso aplicados de verdade. Por isso um alvo fora de faixa é
      truncado no limite, e por isso o comando <code>A</code> (await) existe:
      ele só responde quando o movimento termina.
    </p>

    <h3>Como as peças se encaixam</h3>
    <table>
      <tr><th>Módulo</th><th>Responsabilidade</th></tr>
      <tr><td><code>device.py</code></td><td>Os eixos: posição, velocidade, limites, modos. Não sabe nada de serial.</td></tr>
      <tr><td><code>protocol.py</code></td><td>Traduz o ASCII do fabricante em ações nos eixos, e devolve as respostas.</td></tr>
      <tr><td><code>transport_serial.py</code></td><td>A porta RS-485/USB. Só transporta bytes.</td></tr>
      <tr><td><code>gui/</code></td><td>Observa o dispositivo e comanda pelo mesmo protocolo.</td></tr>
    </table>
    """


def _interface_guide() -> str:
    return """
    <h2>A interface, painel por painel</h2>

    <h3>Conexão (RS-485 / USB)</h3>
    <p>
      Só é necessária quando outro programa vai comandar o simulador. Escolha
      a porta (<b>Atualizar</b> relista), o tipo de interface e o baud rate,
      e clique em <b>Conectar</b>. A partir daí, o que chegar pela porta move
      a unidade e aparece no log.
    </p>
    <p>
      <b>USB / RS-232</b> e <b>RS-485 half-duplex</b> falam o mesmo protocolo;
      a diferença é elétrica. O modo RS-485 liga o controle de direção por
      RTS. Se o seu adaptador faz isso em hardware, ele avisa e segue.
    </p>
    <p>
      <b>Reconectar automaticamente</b> reabre a porta sozinho se o cabo ou o
      dongle USB cair.
    </p>

    <h3>Telemetria</h3>
    <p>
      Posição em graus <i>e</i> em contagens (a unidade do protocolo),
      resolução vigente, curso permitido, velocidade instantânea e os modos
      ativos. É aqui que se confere se um comando fez o que devia.
    </p>

    <h3>Aba Controle</h3>
    <p>
      Alvos em graus, velocidade em °/s (a interface converte para contagens
      ao montar o comando), jog com passo ajustável, e os botões de
      <b>Halt</b>, <b>Reset</b>, <b>Aguardar</b> e <b>Versão</b>.
    </p>
    <p>
      <b>Modo monitor / auto-scan</b> faz a unidade varrer sozinha entre os
      limites — útil para deixar rodando enquanto se observa outra coisa.
    </p>

    <h3>Aba Configuração</h3>
    <p>
      Micropasso (muda a resolução), modo de limites, modo de controle,
      potência, eco, feedback e execução slaved. Em <b>slaved</b>, os comandos
      de posição ficam pendentes e os dois eixos partem juntos no
      <code>A</code>.
    </p>

    <h3>Aba Terminal DPCL</h3>
    <p>
      Envia comandos ASCII crus e mostra todo o tráfego — inclusive o que a
      própria interface gera e o que chega pela porta serial. Digite
      <code>?</code> para a lista de comandos.
    </p>
    """


def _test_modes() -> str:
    return """
    <h2>Modos de teste</h2>
    <p class="lead">Do mais simples ao mais próximo do equipamento real.</p>

    <h3>1. Modo local — sem porta nenhuma</h3>
    <p>
      É como o simulador abre. A interface comanda o dispositivo diretamente,
      pelo mesmo interpretador do protocolo. Serve para conhecer o
      comportamento, demonstrar o equipamento e validar a parte física
      (tempos de movimento, limites, micropasso) sem nenhuma fiação.
    </p>

    <h3>2. Loopback — duas portas virtuais</h3>
    <p>
      Para exercitar o <b>seu</b> software contra o simulador, sem hardware.
      Crie um par de portas ligadas uma na outra, conecte o simulador em uma
      ponta e aponte seu programa para a outra.
    </p>
    <p><b>Linux</b> (pacote <code>socat</code>):</p>
    <pre>socat -d -d pty,raw,echo=0,link=/tmp/ptu-sim \\
           pty,raw,echo=0,link=/tmp/ptu-cliente</pre>
    <p><b>Windows</b>: instale o com0com, que cria um par COM10 ↔ COM11.</p>
    <p>
      Depois, no painel <b>Conexão</b>, conecte em uma das pontas e rode o seu
      programa (ou <code>tools/ptu_client.py --port &lt;outra&gt; --demo</code>)
      na outra.
    </p>

    <h3>3. Fiação real — RS-485 ou USB</h3>
    <p>
      Com dois conversores no mesmo barramento. Confirme os dois lados com a
      mesma velocidade, paridade e bits de parada (9600 8N1 por padrão) e, em
      RS-485, a polaridade A/B e a terminação de 120 Ω nas duas pontas.
    </p>

    <h3>4. Autoteste de aceitação</h3>
    <p>
      Um comando, sem hardware: sobe o simulador de um lado de um par de
      portas virtuais e, do outro, executa a sequência de um controlador real
      (resolução, limites, movimento com await, movimento combinado, halt e
      limites de usuário), imprimindo PASSOU/FALHOU.
    </p>
    <pre>python3 tools/autoteste.py</pre>
    <p>Requer Linux ou macOS. No Windows, use o roteiro manual e o com0com.</p>

    <h3>5. Suíte automatizada</h3>
    <pre>pip install -e ".[dev]"
pytest</pre>
    <p>
      No Linux, 77 testes passam. No Windows o resultado correto é
      <b>70 passed, 7 skipped</b>: os 7 testes ponta a ponta usam PTYs, que só
      existem em sistemas POSIX.
    </p>

    <h3>Roteiro rápido de verificação visual</h3>
    <table>
      <tr><th>Passo</th><th>O que deve acontecer</th></tr>
      <tr><td>Ir para pan 45°, tilt 20°</td><td>Giro suave; instrumentos acompanham; volta a EM POSIÇÃO</td></tr>
      <tr><td>Movimento longo + Halt</td><td>Para na hora, sem voltar a andar</td></tr>
      <tr><td>Terminal: <code>PR</code></td><td>Responde a resolução em segundos de arco</td></tr>
      <tr><td>Modo monitor</td><td>Varre sozinho entre os limites</td></tr>
      <tr><td>Micropasso → Quarter</td><td>Resolução muda; a unidade <b>não</b> sai do lugar</td></tr>
      <tr><td>Alvo fora do curso</td><td>É truncado no limite, não estoura</td></tr>
    </table>
    """


def _antenna_tracking() -> str:
    return """
    <h2>Geo Pointing Module e rastreamento de antena por GPS</h2>
    <p class="lead">
      O recurso mais avançado do simulador, com os comandos confirmados
      <b>byte a byte contra fotos das páginas reais</b> do "E Series
      Pan-Tilt Command Reference Manual, Version 6.00 (09/2014)" da FLIR
      — Capítulo 17, "Geo Pointing Module".
    </p>

    <h3>1. Posição e orientação próprias (seção 17.3/17.4)</h3>
    <p>
      A unidade guarda sua própria pose geográfica — onde está instalada
      (latitude, longitude, altitude) e como está orientada (roll, pitch,
      yaw) — como base para o apontamento geográfico:
    </p>
    <pre>GL              consulta latitude própria      -> * -23.500000
GL-23.5         define a latitude própria
GO              consulta longitude própria     -> * -46.600000
GO-46.6         define a longitude própria
GA              consulta altitude própria (m)  -> * 760.000000
GA760           define a altitude própria
GLLA            consulta os 3 juntos           -> * -23.500000,-46.600000,760.000000
GLLA-23.5,-46.6,760   define os 3 juntos

GR / GP / GY    consulta/define roll/pitch/yaw próprios, em graus
GRPY            consulta/define os 3 juntos (mesmo formato de GLLA)
GCP             consulta/define o offset de pitch da câmera (payload)</pre>
    <p>
      Consulta e definição sempre respondem com o valor atual formatado
      em <b>6 casas decimais</b> — diferente do <code>*\\r\\n</code> seco
      que os comandos de posição de eixo (<code>PP</code>/<code>TP</code>)
      usam ao definir. Confirmado pelo exemplo do manual (seção 17.4.3).
      Use a aba "Rastreamento GPS" → grupo <b>"Posição própria da
      unidade"</b> para testar pela GUI.
    </p>

    <h3>2. Apontar para um alvo agora — comando real GG (seção 17.5)</h3>
    <p>
      <b><code>GG&lt;lat&gt;,&lt;lon&gt;,&lt;alt&gt;</code> é o comando
      real da FLIR</b> que manda o PTU apontar para qualquer coordenada
      geográfica na hora — a peça que faltava para o rastreamento de
      antena de verdade:
    </p>
    <pre>GG                        consulta a última posição apontada -> * -22.90000,-43.20000,0.00000
GG-22.9,-43.2,0           aponta para a coordenada agora     -> *
GG1                       aponta para o landmark salvo no índice 1
GGD                       distância (m) até o aim point atual
GGD1,0,0                  distância (m) até um ponto informado (não move nada)</pre>
    <p>
      Repare: ao contrário de <code>GLLA</code>/<code>GRPY</code>, a
      <b>definição de <code>GG</code> responde só <code>*</code></b> (sem
      ecoar o valor) — é uma <b>ação</b>, como <code>PP</code>/<code>TP</code>,
      não um campo de configuração. A consulta usa <b>5 casas
      decimais</b> (diferente das 6 da seção 17.4), confirmado pelo
      exemplo do manual.
    </p>
    <p>
      <b>Rastrear um veículo em movimento é chamar <code>GG</code> de
      novo a cada posição de GPS recebida</b> — o mesmo princípio de uma
      estação terrena de satélite. Não existe um modo "ligar/desligar
      rastreamento" no protocolo real: cada <code>GG</code> aponta na
      hora. A trajetória de demonstração da aba "Rastreamento GPS" faz
      exatamente isso, enviando <code>GG</code> repetidamente.
    </p>
    <p>
      <b>Importante:</b> isto não é orientação de armas nem rastreamento
      ativo de um alvo não cooperativo. O comando só sabe apontar para
      onde um receptor GPS <i>a bordo do próprio veículo</i> diz que ele
      está — a mesma função que uma parabólica de estação terrena faz ao
      seguir um satélite.
    </p>

    <h3>3. Landmarks — GM/GMA/GMN/GMD/GMC (seção 17.5)</h3>
    <pre>GMA&lt;nome&gt;,&lt;lat&gt;,&lt;lon&gt;,&lt;alt&gt;   salva um landmark
GM                          lista todos os landmarks salvos
GM&lt;índice&gt;                consulta um landmark específico
GMN                         número de landmarks salvos
GMD / GMD&lt;índice&gt;         apaga o último / um específico
GMC                         apaga todos</pre>
    <p>
      Pontos de referência de posição conhecida, usados na calibração da
      unidade (apontar fisicamente para eles e salvar) e como atalho para
      apontar de novo (<code>GG&lt;índice&gt;</code>).
    </p>

    <h3>O que ainda não foi confirmado</h3>
    <p>
      <code>GC</code> (calibrar), <code>GS</code> (status), <code>GDR</code>
      (restaurar última configuração) e <code>GT</code> (tipo de ponto)
      fazem parte do mesmo capítulo, mas a sintaxe exata ainda não foi
      fotografada — não estão implementados neste simulador. Ver
      <code>docs/PROTOCOL.md</code> para os detalhes e as fontes.
    </p>

    <h3>A matemática por trás</h3>
    <p>
      Duas posições geodésicas (latitude, longitude, altitude — o formato
      que qualquer GPS entrega, no datum WGS84) viram um vetor
      azimute/elevação/distância por um caminho de três passos:
    </p>
    <ol>
      <li>Geodésico → <b>ECEF</b> (Earth-Centered, Earth-Fixed): coordenadas
          cartesianas com origem no centro da Terra.</li>
      <li>ECEF → <b>ENU</b> (East-North-Up): projeção no plano tangente
          local da estação de solo.</li>
      <li>Azimute = atan2(Leste, Norte); Elevação = atan2(Cima, distância
          horizontal).</li>
    </ol>
    <p>
      É o método padrão de rastreamento de antena (o mesmo do Gpredict e
      de estações terrenas de satélite) — não uma aproximação de Terra
      plana. Implementado em <code>pantiltsim/tracking.py</code>
      (<code>look_angles</code>, usado por <code>GG</code>/<code>GGD</code>).
    </p>

    <h3>Usando pela aba "Rastreamento GPS"</h3>
    <table>
      <tr><th>Passo</th><th>O que fazer</th></tr>
      <tr><td>1</td><td>Preencha latitude/longitude/altitude em <b>"Posição própria da unidade"</b> e clique em <b>Definir posição (GLLA)</b>.</td></tr>
      <tr><td>2</td><td>Preencha a posição do <b>alvo</b> e clique em <b>Apontar (GG)</b> — ou use a trajetória de demonstração abaixo, que envia <code>GG</code> repetidamente.</td></tr>
      <tr><td>3</td><td>Acompanhe azimute, elevação e distância calculados no painel "Apontamento atual".</td></tr>
    </table>
    <p>
      A <b>trajetória de demonstração</b> simula o feed de GPS de um
      veículo com rumo, velocidade e taxa de subida constantes — útil
      para ver o rastreamento em ação sem hardware GPS real.
    </p>
    """


def _command_reference() -> str:
    return """
    <h2>Comandos do protocolo do fabricante</h2>
    <p class="lead">
      Formato: <code>&lt;eixo&gt;&lt;código&gt;[valor]</code>, terminado por
      espaço ou Enter. Sem valor, o comando vira consulta. Resposta de
      sucesso começa com <code>*</code>; erro, com <code>!</code>.
      Valores em contagens.
    </p>

    <h3>Posição e velocidade</h3>
    <table>
      <tr><th>Comando</th><th>Faz</th><th>Consulta devolve</th></tr>
      <tr><td><code>PP</code> / <code>TP</code></td><td>Posição absoluta</td><td>Posição atual</td></tr>
      <tr><td><code>PO</code> / <code>TO</code></td><td>Deslocamento relativo</td><td>Posição alvo</td></tr>
      <tr><td><code>PS</code> / <code>TS</code></td><td>Velocidade desejada</td><td>Velocidade alvo</td></tr>
      <tr><td><code>PD</code> / <code>TD</code></td><td>Ajuste relativo de velocidade</td><td>Velocidade instantânea</td></tr>
      <tr><td><code>PA</code> / <code>TA</code></td><td>Aceleração</td><td>Aceleração</td></tr>
      <tr><td><code>PB</code> / <code>TB</code></td><td>Velocidade base</td><td>Velocidade base</td></tr>
      <tr><td><code>PU</code> / <code>TU</code></td><td>Limite superior de velocidade</td><td>Limite superior</td></tr>
      <tr><td><code>PL</code> / <code>TL</code></td><td>Limite inferior de velocidade</td><td>Limite inferior</td></tr>
      <tr><td><code>B</code></td><td colspan="2"><code>B&lt;pan&gt;,&lt;tilt&gt;,&lt;vel_pan&gt;,&lt;vel_tilt&gt;</code> — move os dois de uma vez</td></tr>
    </table>

    <h3>Resolução e limites de curso</h3>
    <table>
      <tr><th>Comando</th><th>Faz</th></tr>
      <tr><td><code>PR</code> / <code>TR</code></td><td>Resolução em segundos de arco por contagem (só leitura)</td></tr>
      <tr><td><code>PN</code> / <code>PX</code></td><td>Consulta limite mínimo / máximo vigente do pan</td></tr>
      <tr><td><code>TN</code> / <code>TX</code></td><td>Idem para o tilt</td></tr>
      <tr><td><code>PNU</code> / <code>PXU</code></td><td>Define limite mínimo / máximo de <b>usuário</b> do pan</td></tr>
      <tr><td><code>LE</code> / <code>LU</code> / <code>LD</code></td><td>Limites de fábrica / de usuário / desabilitados</td></tr>
    </table>
    <p>
      Cuidado com a nomenclatura: <code>LU</code> é "limites de <b>usuário</b>",
      não "limite superior" — o limite superior de velocidade é <code>PU</code>.
      E <code>PD</code> é velocidade, não posição.
    </p>

    <h3>Movimento e modos</h3>
    <table>
      <tr><th>Comando</th><th>Faz</th></tr>
      <tr><td><code>H</code> / <code>HP</code> / <code>HT</code></td><td>Para tudo / só o pan / só o tilt</td></tr>
      <tr><td><code>A</code></td><td>Aguarda o movimento terminar (só responde no fim)</td></tr>
      <tr><td><code>I</code> / <code>S</code></td><td>Execução imediata / slaved (parte junto no <code>A</code>)</td></tr>
      <tr><td><code>CI</code> / <code>CV</code></td><td>Modo posição / velocidade contínua</td></tr>
      <tr><td><code>ME</code> / <code>MD</code></td><td>Liga / desliga o monitor (auto-scan)</td></tr>
      <tr><td><code>WP&lt;m&gt;</code> / <code>WT&lt;m&gt;</code></td><td>Micropasso: F, H, Q, E, A</td></tr>
      <tr><td><code>R</code> / <code>RP</code> / <code>RT</code></td><td>Reset de ambos / do pan / do tilt</td></tr>
    </table>

    <h3>Enlace</h3>
    <table>
      <tr><th>Comando</th><th>Faz</th></tr>
      <tr><td><code>ED</code> / <code>EE</code></td><td>Desliga / liga o eco dos comandos</td></tr>
      <tr><td><code>FT</code> / <code>FV</code></td><td>Feedback terso (<code>* valor</code>) / verboso</td></tr>
      <tr><td><code>V</code></td><td>Versão de firmware</td></tr>
      <tr><td><code>DS</code> / <code>DR</code> / <code>DF</code></td><td>Salvar / restaurar / padrões de fábrica</td></tr>
    </table>

    <h3>Geo Pointing Module (confirmado byte a byte contra o manual real)</h3>
    <table>
      <tr><th>Comando</th><th>Faz</th></tr>
      <tr><td><code>GL</code> / <code>GO</code> / <code>GA</code></td><td>Latitude / longitude / altitude (m) próprias da unidade</td></tr>
      <tr><td><code>GLLA</code></td><td>Latitude,longitude,altitude próprias, juntas</td></tr>
      <tr><td><code>GR</code> / <code>GP</code> / <code>GY</code></td><td>Roll / pitch / yaw próprios da unidade, em graus</td></tr>
      <tr><td><code>GRPY</code></td><td>Roll,pitch,yaw próprios, juntos</td></tr>
      <tr><td><code>GCP</code></td><td>Offset de pitch da câmera/payload</td></tr>
      <tr><td><code>GG</code></td><td>Aponta para <code>&lt;lat&gt;,&lt;lon&gt;,&lt;alt&gt;</code> ou landmark <code>&lt;índice&gt;</code> agora; sem valor, consulta o último aim point</td></tr>
      <tr><td><code>GGD</code></td><td>Distância (m) até o aim point atual, ou até um ponto informado</td></tr>
      <tr><td><code>GM</code>/<code>GMA</code>/<code>GMN</code>/<code>GMD</code>/<code>GMC</code></td><td>Lista/salva/conta/apaga landmarks</td></tr>
    </table>
    <p>
      <code>GL</code>/<code>GO</code>/<code>GA</code>/<code>GLLA</code>/<code>GR</code>/<code>GP</code>/<code>GY</code>/<code>GRPY</code>/<code>GCP</code>:
      consulta e definição sempre respondem <code>* &lt;valor&gt;</code>
      com 6 casas decimais. <code>GG</code> como ação (definir) responde
      só <code>*</code>; como consulta, 5 casas decimais. Ver o tópico
      <b>Geo Pointing Module e rastreamento de antena por GPS</b> nesta
      ajuda para o detalhamento completo.
    </p>

    <h3>Abertura recomendada, no seu software</h3>
    <pre>ED          desliga o eco
FT          respostas ficam "* &lt;valor&gt;"
PR / TR     resolução -> contagens_por_grau = 3600 / resolução</pre>
    <p>
      E leia a resposta <b>até a linha que começa com <code>*</code> ou
      <code>!</code></b> — nunca com um <code>sleep</code> de tempo fixo. É
      isso que mantém o enlace sincronizado em comandos demorados como o
      <code>A</code>.
    </p>
    """


_TOPICS = [
    ("Primeiros passos", _quick_start),
    ("O núcleo do projeto", _core_concepts),
    ("A interface", lambda device: _interface_guide()),
    ("Modos de teste", lambda device: _test_modes()),
    ("Geo Pointing Module e rastreamento GPS", lambda device: _antenna_tracking()),
    ("Comandos DPCL", lambda device: _command_reference()),
]


class HelpDialog(QDialog):
    """Janela de ajuda com os tópicos à esquerda e o conteúdo à direita."""

    def __init__(self, device: PanTiltDevice, parent=None, topic: int = 0):
        super().__init__(parent)
        self.setWindowTitle("Ajuda do simulador PTU-D300E")
        self.resize(860, 620)

        self.topics = QListWidget()
        self.topics.setMaximumWidth(190)
        self.pages = QStackedWidget()

        for title, builder in _TOPICS:
            self.topics.addItem(title)
            browser = QTextBrowser()
            browser.setOpenExternalLinks(True)
            browser.setHtml(_CSS + builder(device))
            self.pages.addWidget(browser)

        self.topics.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.topics.setCurrentRow(max(0, min(topic, len(_TOPICS) - 1)))

        content = QHBoxLayout()
        content.addWidget(self.topics)
        content.addWidget(self.pages, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addLayout(content, stretch=1)
        layout.addWidget(buttons)

    @staticmethod
    def topic_index(name: str) -> int:
        for index, (title, _) in enumerate(_TOPICS):
            if title == name:
                return index
        return 0


def terminal_help_text(device: PanTiltDevice) -> str:
    """Resumo de comandos impresso no log quando o usuário digita '?'."""
    pan = device.pan
    return (
        "──────── ajuda rápida do terminal DPCL ────────\n"
        "Formato: <eixo><código>[valor]   eixo = P (pan) ou T (tilt)\n"
        "Sem valor o comando vira consulta. Valores em CONTAGENS.\n"
        f"Agora: {pan.counts_per_degree:.2f} contagens por grau "
        f"({pan.arcsec_per_count:.4f} segundos de arco por contagem)\n"
        f"  ex.: 45° de pan = {pan.deg_to_counts(45.0)} contagens -> PP{pan.deg_to_counts(45.0)}\n"
        "\n"
        "  PP / TP   posição absoluta      PR / TR   resolução (só leitura)\n"
        "  PO / TO   deslocamento relativo PN / PX   limites de curso do pan\n"
        "  PS / TS   velocidade            PNU/ PXU  limites de usuário\n"
        "  PD / TD   velocidade atual      LE/LU/LD  limites fábrica/usuário/off\n"
        "  PA / TA   aceleração            CI / CV   modo posição / velocidade\n"
        "  H HP HT   para tudo / pan / tilt  ME / MD  monitor (auto-scan)\n"
        "  A         aguarda o movimento   I / S     execução imediata / slaved\n"
        "  R RP RT   reset ambos/pan/tilt  WP<m>     micropasso F H Q E A\n"
        "  ED / EE   eco off / on          FT / FV   feedback terso / verboso\n"
        "  V         versão                B         B<pan>,<tilt>,<vp>,<vt>\n"
        "\n"
        "  -- Geo Pointing Module (Cap. 17 do manual, confirmado byte a byte) --\n"
        "  GL / GO / GA   latitude / longitude / altitude(m) próprias\n"
        "  GLLA           os 3 juntos, separados por vírgula\n"
        "  GR / GP / GY   roll / pitch / yaw próprios (graus)\n"
        "  GRPY           os 3 juntos       GCP   offset de pitch da câmera\n"
        "  GG<lat,lon,alt> aponta para lá agora    GG<índice> aponta para landmark\n"
        "  GGD             distância até o aim point\n"
        "  GMA<nome,lat,lon,alt> salva landmark    GM/GMN/GMD/GMC  lista/conta/apaga\n"
        "\n"
        "Digite ?? para abrir a janela de ajuda completa (ou tecle F1).\n"
        "───────────────────────────────────────────────"
    )
