#!/usr/bin/env bash
# Instalador offline do simulador PTU-D300E para BeagleBone (sem internet).
#
# Uso (na BeagleBone, depois de copiar todo o repositório do pendrive
# para o disco local — não rode direto do pendrive):
#
#   cd ~/PAN-TILT-SIMULATOR/deploy/beaglebone
#   ./install.sh
#
# O que faz, nesta ordem:
#   1. Confere Python 3.9+ e o módulo venv.
#   2. Cria um ambiente virtual em ~/.pantiltsim-venv.
#   3. Instala setuptools, wheel e pyserial a partir dos .whl locais
#      em wheels/ (nenhum acesso à rede — usa --no-index).
#   4. Instala o pacote pantiltsim em modo editável, a partir do
#      próprio repositório (também sem rede).
#   5. Roda uma verificação: consulta a versão e, se possível,
#      tools/autoteste.py (que não precisa de rede nem de hardware).
#   6. Deixa um atalho `ptu-sim` pronto para uso e mostra os comandos.
#
# Todos os pacotes em wheels/ são puro-Python (nenhuma extensão
# compilada), então funcionam em qualquer arquitetura sem recompilar —
# inclusive no ARM da BeagleBone. Este instalador NÃO inclui o PyQt5
# (a interface gráfica): a BeagleBone é o alvo do modo headless por
# definição (normalmente sem monitor); rode a GUI no PC que comanda o
# pan-tilt, não na própria placa.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WHEELS_DIR="$SCRIPT_DIR/wheels"
VENV_DIR="${PANTILTSIM_VENV:-$HOME/.pantiltsim-venv}"
MIN_PYTHON_MINOR=9

# -- cores (desligadas se a saída não for um terminal) ----------------------
if [ -t 1 ]; then
    C_OK="\033[32m"; C_ERR="\033[31m"; C_WARN="\033[33m"; C_RESET="\033[0m"
else
    C_OK=""; C_ERR=""; C_WARN=""; C_RESET=""
fi

ok()   { printf "  ${C_OK}[OK]${C_RESET}    %s\n" "$1"; }
err()  { printf "  ${C_ERR}[ERRO]${C_RESET}  %s\n" "$1"; }
warn() { printf "  ${C_WARN}[AVISO]${C_RESET} %s\n" "$1"; }
step() { printf "\n== %s ==\n" "$1"; }

fail() {
    err "$1"
    echo
    echo "Instalação interrompida. Nada além do ambiente virtual em"
    echo "'$VENV_DIR' foi tocado — pode apagar essa pasta e tentar de novo"
    echo "sem medo de deixar o sistema pela metade."
    exit 1
}

# ---------------------------------------------------------------------------
step "Verificando o ambiente"

case "$SCRIPT_DIR" in
    /media/*|/mnt/*|/run/media/*)
        warn "Este script parece estar rodando direto do pendrive ($SCRIPT_DIR)."
        warn "Copie a pasta do repositório inteira para o disco local antes de"
        warn "instalar (ex.: cp -r /media/*/PAN-TILT-SIMULATOR ~/) — pendrives"
        warn "em FAT32/exFAT costumam falhar silenciosamente com venv/pip."
        ;;
esac

if ! command -v python3 >/dev/null 2>&1; then
    fail "python3 não encontrado. Instale o Python 3.9+ do sistema antes de continuar."
fi

PY_VERSION="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PY_MINOR="$(python3 -c 'import sys; print(sys.version_info[1])')"
PY_MAJOR="$(python3 -c 'import sys; print(sys.version_info[0])')"

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt "$MIN_PYTHON_MINOR" ]; }; then
    fail "Python $PY_VERSION encontrado; este projeto precisa de 3.$MIN_PYTHON_MINOR ou mais novo."
fi
ok "Python $PY_VERSION"

if ! python3 -c "import venv" >/dev/null 2>&1; then
    fail "Módulo 'venv' indisponível. Nas imagens Debian ele normalmente já vem" \
         "com o Python do sistema; se faltar, precisa do pacote python3-venv" \
         "instalado (via apt, antes de ficar offline, ou via .deb levado no pendrive)."
fi
ok "Módulo venv disponível"

if [ ! -d "$WHEELS_DIR" ] || [ -z "$(ls -A "$WHEELS_DIR" 2>/dev/null)" ]; then
    fail "Pasta de pacotes offline vazia ou ausente: $WHEELS_DIR"
fi
ok "Pacotes offline encontrados em $WHEELS_DIR"

# ---------------------------------------------------------------------------
step "Criando o ambiente virtual"

if [ -d "$VENV_DIR" ]; then
    warn "Já existe um ambiente em $VENV_DIR — reaproveitando."
else
    python3 -m venv "$VENV_DIR" || fail "Falha ao criar o ambiente virtual em $VENV_DIR"
    ok "Criado em $VENV_DIR"
fi

VENV_PY="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

if [ ! -x "$VENV_PY" ]; then
    fail "Ambiente virtual criado, mas '$VENV_PY' não existe — instalação corrompida."
fi

# ---------------------------------------------------------------------------
step "Instalando dependências (offline, a partir de wheels/)"

"$VENV_PIP" install --no-index --find-links="$WHEELS_DIR" \
    --upgrade setuptools wheel \
    || fail "Falha ao instalar setuptools/wheel a partir dos pacotes locais"
ok "setuptools e wheel"

"$VENV_PIP" install --no-index --find-links="$WHEELS_DIR" pyserial \
    || fail "Falha ao instalar pyserial a partir dos pacotes locais"
ok "pyserial"

# ---------------------------------------------------------------------------
step "Instalando o pantiltsim a partir do repositório local"

"$VENV_PIP" install --no-index --no-build-isolation -e "$REPO_ROOT" \
    || fail "Falha ao instalar o pacote pantiltsim"
ok "pantiltsim instalado em modo editável (aponta para $REPO_ROOT)"

# ---------------------------------------------------------------------------
step "Verificando a instalação"

VERSAO="$("$VENV_PY" -m pantiltsim.main --version 2>&1)" \
    || fail "pantiltsim instalado mas 'pantiltsim.main --version' falhou: $VERSAO"
ok "$VERSAO"

if [ "$(uname -s)" = "Linux" ]; then
    if "$VENV_PY" "$REPO_ROOT/tools/autoteste.py" >/tmp/pantiltsim-autoteste.log 2>&1; then
        ok "Autoteste ponta a ponta (protocolo + movimento) passou"
    else
        warn "Autoteste não passou — veja /tmp/pantiltsim-autoteste.log"
        warn "A instalação em si está OK; isso indica um problema a investigar"
        warn "separadamente (não interrompe a instalação)."
    fi
fi

# ---------------------------------------------------------------------------
step "Pronto"

cat <<EOF

Ambiente virtual: $VENV_DIR

Para usar, em qualquer sessão nova:
  source $VENV_DIR/bin/activate
  ptu-sim --list-ports
  ptu-sim --headless --port /dev/ttyUSB0 --baud 9600 --rs485

Ou sem ativar o ambiente, direto:
  $VENV_DIR/bin/ptu-sim --headless --port /dev/ttyUSB0 --rs485

Para atualizar depois de um 'git pull' no repositório (sem precisar de
pendrive, se a BeagleBone tiver rede futuramente, ou copiando o
repositório atualizado de novo via pendrive): não é necessário reinstalar
— o pacote está em modo editável e aponta direto para
'$REPO_ROOT'.

Modelo de serviço systemd (início automático, opcional — não é ativado
por este instalador): deploy/beaglebone/pantiltsim.service.example

Ajuda embutida: ptu-sim --help
Procedimento completo: docs/PROCEDIMENTO.md
EOF
