# Instruções para manutenção

Responda em pt-BR. Preserve credenciais. Não envie mensagens a clientes,
publique serviços ou faça push sem autorização explícita do proprietário.
Atualização automática do upstream WuzAPI já foi autorizada nesta implantação.
Publicação de `wuzapi-mcp.filipesantosdev.pro` via Cloudflare também foi autorizada.

Este repositório contém somente o adaptador MCP, testes e documentação.
O WuzAPI e seus dados ficam fora do Git, em `/var/lib/openbot/wuzapi`.

- Use `.venv/bin/pytest -q`; os testes não devem enviar WhatsApp nem depender de números reais.
- Reutilize a API WuzAPI e o FastMCP; não implemente protocolo MCP ou OAuth manualmente.
- Preserve escopos, restrições por instância, redação de segredos e ausência de retry de envios.
- Mudanças em ferramentas alcançam schemas, testes e documentação de conexão.
- Nunca apague dados/sessões para resolver uma falha. Backup vem antes de migração.
- A conta `openbot` opera serviços com `systemctl --user`, sem sudo.
- O catálogo deriva das rotas ativas oficiais; não exponha shell ou destinos HTTP arbitrários.
- `confirmed=true` é declaração do chamador, não aprovação humana verificável.
- Confira `docs/OPERATIONS.md` antes de mexer na implantação ou nos timers.

Mantenha a menor mudança completa. Ao responder, informe o que não foi verificado
e riscos relevantes.
