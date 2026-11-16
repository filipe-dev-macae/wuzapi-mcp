---
name: rotacionar-wuzapi
description: Rotacionar uma chave de cliente do WuzAPI MCP somente quando o titular pedir explicitamente. Aplica-se às chaves MCP de Composio, OpenBot ou outro cliente cadastrado, com acesso local autorizado à VPS.
---

# Rotacionar chave do WuzAPI MCP

Execute somente após pedido explícito de rotação, como “rotacionar WuzAPI
composio” ou “rotacionar WuzAPI openbot”. Um pedido para preparar/documentar o
procedimento não autoriza trocar chaves. Não programe timer ou rotação automática.

Requer shell autorizado na VPS; o MCP remoto não expõe gerência das próprias
chaves. O texto `/rotacionar/WuzAPI composio` pode ser tratado como pedido
conversacional se chegar do titular; não é rota HTTP nem comando slash
registrado em todos os aplicativos. Se faltar o cliente alvo, esclareça-o.

## Fluxo

1. Leia `/srv/wuzapi-mcp/docs/ROTATION.md` e o cadastro pelo CLI `list`, sem
   imprimir segredos. Confirme cliente e quais sistemas dependem dessa chave.
2. Como `openbot`, execute `rotate-prepare CLIENTE` com o arquivo de cadastro
   indicado no guia. Isso cria `CLIENTE-next.key`, mantém a chave antiga válida
   e preserva permissões/instâncias. Se houver transição anterior, examine o
   estado; não sobrescreva nem tente uma segunda rotação.
3. Atualize o segredo no cliente por meio privado. Não cole chave no chat,
   GitHub, query string, argumento de shell ou log. Não mova para pasta pública.
   Se a integração não permitir atualizar aqui, informe o caminho do arquivo
   protegido para o titular e aguarde sua atualização. Não revogue antes disso.
4. Teste uma consulta sem efeitos com a chave nova através do cliente migrado.
   Prefira `get_usage_guide` quando houver `read`; um handshake autenticado
   prova validade da chave, mas não prova que o cliente já a salvou.
5. Com evidência de migração, execute `rotate-finish CLIENTE --client-updated`.
   A autorização original para rotacionar esse cliente cobre a conclusão; não
   peça a mesma autorização de novo. Confira que a nova funciona e a antiga
   foi rejeitada, sem imprimir nenhuma delas. Remova somente cópias de entrega
   antigas identificadas dentro do alcance autorizado.

Se o titular cancelar antes da conclusão, `rotate-cancel CLIENTE` revoga apenas
a chave de transição e preserva a antiga. Se a migração já ocorreu, restaure
o cliente para a chave antiga antes de cancelar. Se uma finalização foi
interrompida, leia o procedimento de recuperação; não apague arquivos por tentativa.

## Limites

Este fluxo troca API Keys dos clientes MCP. Não troca automaticamente tokens
administrativos/sessões do WuzAPI, HMAC, credenciais Cloudflare, GitHub nem a
chave de criptografia dos dados. Não mexa nessas credenciais sem pedido
específico e procedimento próprio. Trocar a chave de criptografia como se fosse
uma API Key pode tornar dados ilegíveis.
