# Evidências de validação

## WuzAPI

Versão usada nos testes reais: commit
`ef36fa4961e10b74b23ffa54d7f9b5c656829fee` do repositório oficial.
Compilada em Linux amd64 com Go 1.26.11 e `CGO_ENABLED=0`.

Antes de criar este adaptador, o titular pareou sua conta por código e confirmou
no WhatsApp que funcionaram:

- Botão de abrir URL.
- Botão de resposta rápida.
- Botão de copiar código fictício.
- Botão de ligação telefônica.
- Combinação de resposta, URL e copiar na mesma mensagem.
- Link preview de um link curto do Mercado Livre, incluindo sua apresentação.

Esses envios foram feitos diretamente pela API WuzAPI. O remetente e o
destinatário eram o mesmo número do titular: a validação foi na conversa consigo
mesmo. Isso não substitui teste de entrega entre contas distintas ou em versões
diferentes de Android, iOS e WhatsApp Web. Não há números, códigos de pareamento,
tokens ou mensagens privadas neste documento.

O relatório local anterior, fora deste repositório, contém os IDs das mensagens
e o procedimento. Não publique bancos, QR Codes ou logs para reproduzir o teste.

## Adaptador MCP

Testes automatizados em `tests/` verificam:

- Mapeamento de botões mistos e `LinkPreview` para os payloads WuzAPI.
- Validação de campos de botão e URLs sem credenciais embutidas.
- Autenticação HTTP: nenhuma chave/chave inválida é rejeitada.
- Handshake MCP `2025-06-18` e descoberta de ferramentas via Streamable HTTP.
- Revogação de chave, escopos e isolamento por ID de instância.
- Ocultação de tokens e segredos nas respostas administrativas.
- Bloqueio de destinos externos, endpoints fora do catálogo e path traversal.
- Ausência de retry automático após timeout e de redirecionamento autenticado.
- Criação, revogação e rotação de chave sem imprimir seu valor.
- Geração do catálogo excluindo rotas comentadas.
- Backup/restauração e rollback preservando o estado da implantação malsucedida.

Na VPS também foram executados:

- Smoke test de um binário candidato com banco e credenciais temporários,
  sem conectar conta WhatsApp.
- Cliente MCP autenticado pela porta real, descoberta de ferramentas e consulta
  de saúde até o backend real.
- Migração da sessão pareada para serviço `systemd --user`.
- Backup consistente real seguido da reinicialização e consulta pelo MCP.
- Consulta de upstream que confirmou a versão já atualizada, sem implantação nova.

Não foram enviados testes novos pelo MCP a uma conta real nesta implementação.
O mapeamento de envio é coberto por testes, mas uma demonstração pelo cliente
final deve ter destinatário/conteúdo autorizados.

## Ainda não validado

- Publicação HTTPS e passagem pela rede Cloudflare.
- Cadastro e chamada reais pelo Composio/ZapIA.
- Aplicação da configuração MCP dentro do OpenBot.
- Inicialização depois de reboot real da VPS.
- Atualização real para um commit futuro; rollback foi exercitado em testes.
- Todos os demais endpoints do catálogo em contas WhatsApp reais.

## Repetir as verificações

```bash
cd /srv/wuzapi-mcp
.venv/bin/pytest -q
```

Para a verificação local com cliente real, consulte `CONNECTORS.md`. Para
atualização, backup e consulta de logs, consulte `OPERATIONS.md`.
