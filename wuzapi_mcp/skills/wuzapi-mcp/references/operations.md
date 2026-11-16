# Manutenção rootless

Esta referência se aplica à implantação documentada na VPS. Um cliente remoto
MCP não ganha shell, acesso a arquivos ou root por ler a skill. Use-a somente
se o agente também tiver acesso Linux autorizado; do contrário, limite-se às
ferramentas da API e descreva o que exige intervenção no servidor.

## Onde operar

- Projeto: `/srv/wuzapi-mcp`; guias completos em `docs/OPERATIONS.md`,
  `docs/SECURITY.md`, `docs/CONNECTORS.md`, `docs/VALIDATION.md` e `docs/WHATSAPP.md`.
- Runtime privado: `/var/lib/openbot/wuzapi`; banco/sessões em `data`,
  credenciais em `secrets`, logs privados em `logs`, snapshots em `backups`.
- Conta Linux `openbot`, sem sudo. `systemd --user` mantém WuzAPI, MCP e túnel;
  linger está habilitado. Nunca remova banco/sessão para corrigir conexão.
- WuzAPI: loopback 8081; MCP: loopback 8082 e endpoint HTTPS documentado no
  projeto. Não publique a API WuzAPI nem copie chaves para pastas públicas.

Comandos como `openbot`:

```bash
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
systemctl --user status wuzapi.service wuzapi-mcp.service wuzapi-tunnel.service
systemctl --user list-timers
```

Leia logs localmente sem colar segredos ou conteúdo de conversas. O journal
global não é legível por essa conta; os logs de serviço privados são a fonte.
Reiniciar só `wuzapi-mcp.service` preserva a sessão WhatsApp. Reiniciar WuzAPI
interrompe temporariamente as conexões; resolva incidentes dentro do alcance
autorizado e confira depois saúde e autenticação.

## Atualização e proteção de dados

O titular autorizou acompanhamento automático da `main` oficial de
`asternic/wuzapi`, com consulta a cada 15 minutos. O timer executa testes/build,
valida o catálogo, cria backup consistente e troca a release com rollback em
falha. Não peça aprovação a cada atualização já coberta por essa autorização.

Isso atualiza o WuzAPI e o catálogo ativo. O adaptador Python e esta skill
não se reescrevem automaticamente; mudança incompatível pode exigir manutenção.
Não altere silenciosamente origin para fork nem mantenha patches fora dessa
política. Testes sem mensagens não comprovam renderização de novos formatos.

Antes de alterar dados/migrar, siga o backup documentado. Restauração substitui
estado e pode retirar do banco ativo mensagens posteriores ao snapshot; não
restaure por tentativa. Backups e releases não têm retenção automática, e
backup só na mesma VPS não cobre perda do disco.

Ao corrigir o MCP, leia os chamadores, preserve escopos/redação de segredos,
rode `.venv/bin/pytest -q` e faça consulta real sem enviar WhatsApp. Mudança
na skill deve passar pelo validador Agent Skills e pelos testes de exposição
no protocolo. O conteúdo é carregado na inicialização: reinicie somente o
MCP para publicar a revisão. Novas ferramentas podem exigir sincronização no
Composio. Não faça push GitHub, envio de mensagens ou teste de escrita por
causa de uma simples solicitação de documentação.
