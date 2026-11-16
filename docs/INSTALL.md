# Instalação e reprodução

Estas instruções são para uma instalação **nova**. A VPS atual já foi preparada.
Não execute a inicialização de segredos sobre uma instalação existente.

## Preparação administrativa única

Ubuntu 24.04, Python 3.12, Git e um usuário Linux dedicado. O administrador faz:

```bash
sudo apt-get update
sudo apt-get install python3.12-venv git
sudo loginctl enable-linger openbot
sudo systemctl start user@999.service
```

`999` é o UID da conta nesta VPS. Em outra máquina, consulte `id -u openbot`.
O usuário continua sem sudo. O linger mantém o gerenciador `systemd --user`
ativo após logout e permite iniciar serviços após reboot.

O administrador também prepara `/srv/wuzapi-mcp` com escrita para a conta.
Nesta VPS, o código é compartilhado entre o administrador `ubuntu` e o grupo
`openbot`, com permissões de grupo para manutenção. Em uma VPS nova pode ser
de propriedade exclusiva de `openbot`.

## Adaptador e dependências

Na conta de execução, clone o repositório privado deste adaptador em
`/srv/wuzapi-mcp`. É necessário acesso autorizado à conta/repositório GitHub
e autenticação Git configurada por meio privado; não coloque tokens na URL.
Ter o conector GitHub em um agente não autentica automaticamente o Git da VPS.

```bash
git clone https://github.com/filipe-dev-macae/wuzapi-mcp.git /srv/wuzapi-mcp
cd /srv/wuzapi-mcp
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/pip install -e . --no-deps
.venv/bin/pytest -q
```

O lock inclui as ferramentas de teste, pois a atualização automática também
executa os testes do adaptador. O servidor é limitado a HTTP autenticado;
não há modo stdio sem autenticação.

## Go local, sem Docker ou compilador C

A versão inicial do WuzAPI usa Go 1.26. Para reproduzir a toolchain validada:

```bash
mkdir -p /srv/wuzapi-mcp/.toolchains
cd /srv/wuzapi-mcp/.toolchains
curl -fsSLO https://go.dev/dl/go1.26.11.linux-amd64.tar.gz
sha256sum -c <<'CHECKSUM'
9849f4e04ee35303714e34fbc3ac8ab44ea3e448a95aa182f91e3b9b79c710ec  go1.26.11.linux-amd64.tar.gz
CHECKSUM
tar -xzf go1.26.11.linux-amd64.tar.gz
rm go1.26.11.linux-amd64.tar.gz
```

Esse artefato é para Linux amd64. Em outra arquitetura escolha o arquivo e o
checksum oficiais correspondentes. O Go pode baixar toolchains exigidas por
versões futuras do upstream pelo mecanismo padrão `GOTOOLCHAIN=auto`.

## WuzAPI separado do repositório MCP

Na conta `openbot` desta VPS, `$HOME` é `/var/lib/openbot`:

```bash
umask 077
mkdir -p "$HOME/wuzapi/secrets" "$HOME/wuzapi/data" "$HOME/wuzapi/releases" "$HOME/wuzapi/logs"
git clone --depth 1 https://github.com/asternic/wuzapi.git "$HOME/wuzapi/source"
```

Compile a versão escolhida, gere o catálogo e monte uma release. Execute como
`openbot`, a partir de `/srv/wuzapi-mcp`:

```bash
task_commit=$(git -C "$HOME/wuzapi/source" rev-parse HEAD)
task_release="$HOME/wuzapi/releases/$task_commit"
mkdir "$task_release"
cd "$HOME/wuzapi/source"
CGO_ENABLED=0 GOMAXPROCS=2 /srv/wuzapi-mcp/.toolchains/go/bin/go test ./...
CGO_ENABLED=0 GOMAXPROCS=2 /srv/wuzapi-mcp/.toolchains/go/bin/go build -o "$task_release/wuzapi" .
cp -a static "$task_release/static"
cp API.md "$task_release/API.md"
printf '%s\n' "$task_commit" > "$task_release/UPSTREAM_COMMIT"
cd /srv/wuzapi-mcp
.venv/bin/python -m wuzapi_mcp.catalog "$HOME/wuzapi/source" "$task_commit" "$task_release/mcp-operations.json"
ln -s "$task_release" "$HOME/wuzapi/current"
```

## Gerar segredos sem imprimi-los

Na conta de execução, execute uma única vez:

```bash
python3 - <<'PY'
from pathlib import Path
import os, secrets
os.umask(0o077)
root = Path.home() / 'wuzapi'
folder = root / 'secrets'
admin = secrets.token_urlsafe(32)
encryption = secrets.token_hex(16)
files = {
    'admin-token': admin + '\n',
    'wuzapi.env': f'WUZAPI_ADMIN_TOKEN={admin}\nWUZAPI_GLOBAL_ENCRYPTION_KEY={encryption}\nWUZAPI_AUTO_PRESENCE=unavailable\nTZ=America/Sao_Paulo\nLOG_LEVEL=info\n',
    'mcp.env': f'WUZAPI_BASE_URL=http://127.0.0.1:8081\nWUZAPI_ADMIN_TOKEN_FILE={folder}/admin-token\nMCP_CLIENTS_FILE={folder}/mcp-clients.json\nMCP_PUBLIC_URL=https://wuzapi-mcp.filipesantosdev.pro\nMCP_HOST=127.0.0.1\nMCP_PORT=8082\nWUZAPI_SOURCE_DIR={root}/current\nWUZAPI_RUNTIME_DIR={root}\nWUZAPI_MCP_PROJECT_DIR=/srv/wuzapi-mcp\nWUZAPI_GO_BIN=/srv/wuzapi-mcp/.toolchains/go/bin/go\nXDG_RUNTIME_DIR=/run/user/{os.getuid()}\nDBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{os.getuid()}/bus\n',
}
if any((folder / name).exists() for name in files):
    raise SystemExit('Configuração existente: não sobrescrita')
for name, value in files.items():
    with (folder / name).open('x') as output:
        output.write(value)
print('Segredos criados em arquivos privados; nenhum valor exibido.')
PY
```

Na migração desta VPS foram reutilizados o token administrativo e a chave de
criptografia da instância de teste. **Não gere outra chave de criptografia
para os dados existentes**: isso pode impedir a recuperação de valores cifrados.

Crie as chaves dos clientes:

```bash
cd /srv/wuzapi-mcp
.venv/bin/python -m wuzapi_mcp.keys create openbot --file "$HOME/wuzapi/secrets/mcp-clients.json"
.venv/bin/python -m wuzapi_mcp.keys create composio --file "$HOME/wuzapi/secrets/mcp-clients.json"
```

## Serviços do usuário

Os templates em `deploy/` assumem o código em `/srv/wuzapi-mcp` e a execução
em `$HOME/wuzapi`. Ajuste os templates antes de instalá-los em outros caminhos.

```bash
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
mkdir -p "$HOME/.config/systemd/user"
cp /srv/wuzapi-mcp/deploy/*.service /srv/wuzapi-mcp/deploy/*.timer "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable --now wuzapi.service wuzapi-mcp.service
systemctl --user enable --now wuzapi-update.timer wuzapi-backup.timer
```

Confira `systemctl --user status wuzapi.service wuzapi-mcp.service` e use o
cliente de consulta em `CONNECTORS.md`. Para comandos de manutenção fora do
systemd, informe o arquivo de configuração:

```bash
cd /srv/wuzapi-mcp
WUZAPI_MCP_ENV_FILE="$HOME/wuzapi/secrets/mcp.env" \
  .venv/bin/python -m wuzapi_mcp.maintenance backup
```

## Publicação por Cloudflare Tunnel

A publicação desta VPS já foi autorizada e executada. Para reproduzir em outra
máquina, crie um túnel **remotamente gerenciado**, dedicado ao MCP, configure o
ingress conforme `deploy/cloudflare-ingress.example.json` e o CNAME proxied do
subdomínio para `<ID_DO_TUNEL>.cfargotunnel.com`. Não sobrescreva registros existentes.

Instale o binário oficial `cloudflared` em `.toolchains/cloudflared`, confira
o checksum oficial do release e permita execução pela conta `openbot`.
Armazene o token do túnel em `$HOME/wuzapi/secrets/cloudflared-token`, com
permissão `600`, e habilite `wuzapi-tunnel.service`. O serviço usa `--token-file`;
não inclua o token diretamente no comando, em arquivos versionados ou em URLs.
