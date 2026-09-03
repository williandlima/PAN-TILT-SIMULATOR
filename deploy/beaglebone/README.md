# Instalação offline na BeagleBone (via pendrive)

Pacote autossuficiente para instalar o simulador numa BeagleBone **sem
acesso à internet**. Os três pacotes Python de que o núcleo do simulador
depende (`pyserial`, mais `setuptools`/`wheel` para a instalação em si)
já vêm baixados em [`wheels/`](wheels/) — não falta nada para buscar na
hora H. Todos são puro-Python (sem extensão compilada), então funcionam
em qualquer arquitetura, incluindo o ARM da BeagleBone, sem recompilar.

Não inclui o PyQt5 (interface gráfica): a BeagleBone é o alvo do **modo
headless** por definição — a GUI roda no computador que comanda o
pan-tilt, não na própria placa (ver `docs/PROCEDIMENTO.md`).

## No computador com internet (uma vez)

Nada para "compilar" — os `.whl` já estão no repositório. Só precisa
levar a pasta inteira do projeto para o pendrive:

```bash
git pull                      # garante que deploy/beaglebone/wheels/ está atualizado
```

Copie a pasta `PAN-TILT-SIMULATOR` inteira (não só `deploy/beaglebone`)
para o pendrive — o instalador precisa do repositório completo ao lado.

## Na BeagleBone, sem internet

1. **Copie do pendrive para o disco local antes de instalar.** Rodar
   direto do pendrive costuma falhar (FAT32/exFAT não suporta os links
   simbólicos e permissões que `venv`/`pip` usam):

   ```bash
   cp -r /media/*/PAN-TILT-SIMULATOR ~/
   cd ~/PAN-TILT-SIMULATOR/deploy/beaglebone
   ```

2. Rode o instalador:

   ```bash
   ./install.sh
   ```

   Ele confere o Python, cria um ambiente virtual em
   `~/.pantiltsim-venv`, instala tudo a partir de `wheels/` (com
   `--no-index`, nunca toca a rede), instala o `pantiltsim` a partir do
   próprio repositório copiado, e termina rodando o autoteste
   (`tools/autoteste.py`) para provar que ficou funcional — sem precisar
   de hardware nem de rede para essa verificação.

3. Ao final, o script imprime os comandos prontos para usar. Resumo:

   ```bash
   source ~/.pantiltsim-venv/bin/activate
   ptu-sim --headless --port /dev/ttyUSB0 --baud 9600 --rs485
   ```

## Atualizando depois

Como a instalação é em modo editável (`pip install -e`), atualizar o
código é só trazer uma cópia mais nova do repositório (outro pendrive, ou
`git pull` se a placa ganhar rede depois) para o mesmo caminho — não
precisa rodar `install.sh` de novo, a menos que uma dependência nova
tenha sido adicionada ao projeto (nesse caso, baixe o novo `.whl` num
computador com internet, coloque em `wheels/` e rode o instalador de
novo).

## Início automático no boot (opcional)

[`pantiltsim.service.example`](pantiltsim.service.example) é um modelo
de serviço systemd para subir o simulador sozinho quando a BeagleBone
liga. Não é ativado pelo instalador — leia os comentários no arquivo
para ativar manualmente quando (e se) fizer sentido para o seu caso.

## Se faltar alguma dependência nova no futuro

Se o projeto crescer e passar a depender de outro pacote Python, baixe o
`.whl` correspondente num computador com internet e Python da mesma
versão maior (3.x) — para pacotes puro-Python, a versão exata do Python
não importa; para pacotes com extensão compilada (C/C++), importa a
arquitetura, e aí precisaria baixar especificamente para ARM:

```bash
pip download --no-deps --dest deploy/beaglebone/wheels <pacote>
```

Copie o novo arquivo para dentro de `wheels/` e leve tudo de novo no
pendrive.
