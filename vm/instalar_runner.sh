#!/usr/bin/env bash
# Instala un runner de GitHub Actions en una VM de Madrid (Oracle Cloud Always Free, Ubuntu).
# Uso:  bash instalar_runner.sh <TOKEN_DE_REGISTRO>
# El token sale de GitHub: repo > Settings > Actions > Runners > New self-hosted runner (caduca en 1 h).
set -euo pipefail
REPO_URL="https://github.com/nachoam83-lang/LigaFutbol"
TOKEN="${1:?Falta el token de registro del runner}"

echo "== 1/4 Prueba de acceso a ECM desde esta IP =="
CODIGO=$(curl -s -o /dev/null -w "%{http_code}" -m 20 "https://juegosdeportivos.ecmadrid.org/api/CompeticionesPorDeporte?action=ObtenerCompeticionesDeporteListado&IdDeporte=1&IdTemporada=12&elementoTodas=false&soloActivas=true" || true)
echo "ECM responde HTTP $CODIGO (debe ser 200)"
[ "$CODIGO" = "200" ] || { echo "ECM no deja entrar desde esta IP: no sigas, esta VM no sirve."; exit 1; }

echo "== 2/4 Paquetes =="
sudo apt-get update -y && sudo apt-get install -y git curl python3 python3-venv jq

echo "== 3/4 Descarga del runner =="
ARCH=$(uname -m); [ "$ARCH" = "aarch64" ] && RA=arm64 || RA=x64
VER=$(curl -s https://api.github.com/repos/actions/runner/releases/latest | jq -r .tag_name | sed 's/^v//')
mkdir -p "$HOME/actions-runner" && cd "$HOME/actions-runner"
curl -sL -o r.tar.gz "https://github.com/actions/runner/releases/download/v${VER}/actions-runner-linux-${RA}-${VER}.tar.gz"
tar xzf r.tar.gz && rm r.tar.gz

echo "== 4/4 Registro como servicio (arranca solo al reiniciar) =="
./config.sh --unattended --url "$REPO_URL" --token "$TOKEN" --name "madrid-oracle" --labels "madrid" --replace
sudo ./svc.sh install "$USER" && sudo ./svc.sh start
echo "Listo. En GitHub > Settings > Secrets and variables > Actions > Variables crea RUNNER = madrid"
