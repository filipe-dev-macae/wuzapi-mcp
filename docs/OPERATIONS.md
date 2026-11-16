# Operação e recuperação

## Caminhos nesta VPS

| Caminho | Conteúdo |
| --- | --- |
| `/srv/wuzapi-mcp` | Código Git, testes, documentação e venv do MCP |
| `/srv/wuzapi-mcp/.toolchains/go` | Compilador Go local, fora do Git |
| `/srv/wuzapi-mcp/.toolchains/ffmpeg` | Conversão de GIF/vídeo para stickers |
| `/var/lib/openbot/wuzapi/source` | Checkout do repositório oficial |
| `/var/lib/openbot/wuzapi/releases/<commit>` | Binário, assets e catálogo por versão |
| `/var/lib/openbot/wuzapi/current` | Symlink para a release ativa |
| `/var/lib/openbot/wuzapi/data` | SQLite e sessões |
| `/var/lib/openbot/wuzapi/secrets` | Tokens, chave de criptografia, configurações e chaves MCP |
| `/var/lib/openbot/wuzapi/backups` | Backups consistentes, privados |
| `/var/lib/openbot/wuzapi/failed-state` | Estado preservado ao fazer rollback |
| `/var/lib/openbot/wuzapi/last-update.json` | Resultado da última manutenção |
| `/var/lib/openbot/wuzapi/maintenance-commands.log` | Saída privada de builds, testes e comandos |
| `/var/lib/openbot/wuzapi/logs` | Logs privados dos serviços, legíveis por `openbot` |

A pasta de teste anterior foi mantida em
`/var/lib/openbot/wuzapi-capability-test` como cópia pré-migração. O processo
antigo foi encerrado antes da cópia; não o reinicie em paralelo ao serviço
definitivo, para não usar a mesma identidade de dispositivo duas vezes.

## Comandos sem root

O WuzAPI recebe em `secrets/wuzapi.env` um PATH que inclui
`/srv/wuzapi-mcp/.toolchains`. O FFmpeg foi copiado de uma instalação local
existente e executado como `openbot`; os fixtures de áudio/vídeo/GIF foram
decodificados antes dos envios. Para reproduzir em outra VPS, disponibilize um
FFmpeg compatível e ajuste esse PATH. Ele não é atualizado pelo timer WuzAPI.
Fixtures e evidências privadas dos testes manuais ficam em
`/var/lib/openbot/wuzapi/manual-tests`, fora do Git. O receptor HTTP temporário
usado na validação foi desligado e sua regra de túnel removida.

Execute como `openbot`. Fora de uma sessão de login comum, prepare o acesso ao bus:

```bash
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
systemctl --user status wuzapi.service wuzapi-mcp.service wuzapi-tunnel.service
systemctl --user list-timers
tail -n 100 "$HOME/wuzapi/logs/wuzapi.log" "$HOME/wuzapi/logs/mcp.log"
```

Reiniciar o WuzAPI interrompe temporariamente as conexões. Reiniciar somente o
MCP não encerra as sessões do WhatsApp:

```bash
systemctl --user restart wuzapi-mcp.service
systemctl --user restart wuzapi.service
```

Os serviços estão habilitados e o linger foi ativado administrativamente.
Eles devem iniciar após reboot; não foi reiniciada a VPS durante a validação.
Como `openbot` tem UID de conta de sistema, o journal não é legível por ela
nesta VPS. Cada serviço grava em `logs/*.log` com permissão `600`, sem conceder
acesso aos logs globais do servidor. Logs são anexados e não têm rotação
automática nesta versão; monitore seu tamanho.

## Publicação HTTPS

O endpoint `https://wuzapi-mcp.filipesantosdev.pro/mcp` passa por um túnel
remotamente gerenciado no Cloudflare. Apenas o MCP recebe tráfego público;
WuzAPI e MCP continuam em loopback, e nenhuma porta de entrada adicional da
VPS foi aberta. `/healthz` é uma consulta pública mínima; `/mcp` exige Bearer.

O serviço `wuzapi-tunnel.service` roda como `openbot` e usa
`secrets/cloudflared-token`. O token permite executar esse túnel; a VPS não
recebeu um token geral de administração da conta Cloudflare. Os identificadores
do túnel/DNS estão em `secrets/cloudflare-deployment.json`, incluídos nos backups
de segredos. Regras de ingress são gerenciadas no Cloudflare, conforme modelo
`deploy/cloudflare-ingress.example.json`.

```bash
systemctl --user status wuzapi-tunnel.service
tail -n 100 "$HOME/wuzapi/logs/tunnel.log"
```

Binário local: `/srv/wuzapi-mcp/.toolchains/cloudflared`, versão `2026.11.0`,
SHA-256 `51f7c68b57ed7269164075d7e789efce5b59355982f06392deeb037d982a51fd`.
Foi obtido do release oficial do Cloudflare e conferido antes da execução.
Atualização desse binário é separada da atualização automática do WuzAPI.

Para retirar a publicação, pare/desabilite `wuzapi-tunnel.service` e remova
somente o CNAME deste endpoint no Cloudflare. Os serviços locais e a sessão
WhatsApp continuam funcionando. Nunca remova registros de outros serviços.

## Atualização automática autorizada

`wuzapi-update.timer` consulta a branch `main` de `asternic/wuzapi` a cada
15 minutos, mais dispersão de até 60 segundos. É acompanhamento de commits,
não somente releases. O cronograma não inclui tempo de build/teste.

1. Confere origin oficial e preserva alterações locais não commitadas, bloqueando
   a atualização se o checkout estiver sujo.
2. Busca `main`; se o commit ativo já é o atual, termina sem reiniciar serviços.
3. Cria worktree temporária, executa os testes Go e compila sem C.
4. Extrai catálogo das rotas ativas e verifica endpoints necessários.
5. Executa os testes do MCP e testa uma instância temporária sem conta WhatsApp:
   saúde, rejeição de admin sem autenticação, criação e listagem autenticadas.
6. Para os dois serviços, copia dados e segredos e marca o backup completo.
7. Troca atomicamente o symlink da release, inicia os serviços e testa uma
   consulta autenticada pelo MCP real.
8. Se falhar depois da troca, recupera release, dados e segredos anteriores e
   tenta iniciar novamente. O estado da tentativa fica preservado para análise.

Há um bloqueio para impedir duas manutenções simultâneas. Uma falha de lock ou
de serviço aparece no journal; outras falhas também são registradas em
`last-update.json`. Não há notificações externas automáticas configuradas.

O adaptador não altera o próprio código automaticamente. A sincronização do
catálogo cobre endpoints novos sem adicionar ferramentas. Uma mudança
incompatível pode exigir ajuste de código e impedir a implantação. Os testes
automáticos não enviam WhatsApp e não garantem que o aplicativo ainda renderize
botões; o teste real deve ser repetido após mudanças relevantes.

Para executar/verificar manualmente:

```bash
systemctl --user start wuzapi-update.service
tail -n 100 "$HOME/wuzapi/logs/update.log"
cd /srv/wuzapi-mcp
WUZAPI_MCP_ENV_FILE="$HOME/wuzapi/secrets/mcp.env" \
  .venv/bin/python -m wuzapi_mcp.maintenance status
```

Para desativar atualizações: `systemctl --user disable --now wuzapi-update.timer`.
Se uma execução já estiver ativa, parar o timer não cancela essa execução.
Não interrompa à força a implantação durante cópia/restauração de dados.

## Backups

Há backup diário às **03:20 UTC**, além do backup antes de cada implantação.
Os serviços são parados brevemente para uma cópia consistente de SQLite e
sessões. O backup contém dados e segredos, além do caminho da release anterior.
Os binários anteriores são mantidos em `releases` e devem acompanhar o backup
se for necessário recuperar em outra VPS.

```bash
systemctl --user start wuzapi-backup.service
tail -n 50 "$HOME/wuzapi/logs/backup.log"
```

Backups não são apagados automaticamente. Monitore espaço com
`du -sh "$HOME/wuzapi/backups" "$HOME/wuzapi/releases"` e planeje retenção e cópia
externa. Armazenar somente na mesma VPS não protege contra perda do disco.
Uma verificação de capacidade bloqueia o backup se não houver espaço para a
cópia e uma reserva de 512 MiB; isso não substitui uma política de retenção.

## Restaurar

Somente backups marcados `COMPLETE` e pertencentes à pasta de backups são aceitos.
Identifique o backup correto antes de executar. A operação interrompe os serviços
e reverte o estado lógico do banco para aquele momento:

```bash
cd /srv/wuzapi-mcp
WUZAPI_MCP_ENV_FILE="$HOME/wuzapi/secrets/mcp.env" \
  .venv/bin/python -m wuzapi_mcp.maintenance restore \
  --backup "$HOME/wuzapi/backups/PASTA_DO_BACKUP"
```

O estado substituído é movido para `failed-state`, não apagado. Mensagens ou
alterações recebidas após o snapshot podem deixar de aparecer no banco ativo,
mesmo permanecendo no estado arquivado. Não existe mesclagem automática de bancos.
Backups anteriores à publicação não contêm a credencial do túnel. Para usá-los,
preserve/recupere também `cloudflared-token` do estado arquivado antes de
reiniciar o serviço de túnel.

Se o WhatsApp tiver revogado o dispositivo no lado remoto, restaurar um banco
não desfaz essa revogação; pode ser necessário parear novamente.

## Corrigir o código

O OpenBot pode editar `/srv/wuzapi-mcp`, rodar `.venv/bin/pytest -q` e reiniciar
o serviço MCP. O Git local registra o código do adaptador. O checkout WuzAPI é
separado: edições nele não substituem o binário automaticamente. Compile/teste
uma release antes de trocar `current`; preserve o estado com backup.

O atualizador usa worktrees da versão oficial e não incorpora patches locais.
Se manter um fork, será necessário rever a política de atualização, em vez de
trocar o origin silenciosamente. Não coloque arquivos reais de sessão no Git.
