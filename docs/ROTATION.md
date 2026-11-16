# Rotação manual das API Keys MCP

O titular pediu um procedimento para uso futuro, **sem executar rotação agora**.
Não existe timer de rotação. A atualização automática do WuzAPI não troca essas
chaves. A skill local [rotacionar-wuzapi](../skills/rotacionar-wuzapi/SKILL.md)
fica disponível para invocação explícita; o MCP remoto não ganhou ferramenta
para alterar sua própria autenticação.

## Como pedir

Escreva ao agente com acesso à VPS:

```text
rotacionar WuzAPI composio
rotacionar WuzAPI openbot
```

O agente pode interpretar `/rotacionar/WuzAPI composio` como o mesmo pedido
se receber essa mensagem do titular. Isso não registra um comando slash nos
aplicativos nem publica uma rota web. Clientes que suportam Agent Skills podem
instalar a pasta `skills/rotacionar-wuzapi` e oferecer a invocação própria.
Um agente remoto sem shell não consegue executar esse procedimento somente
pela conexão MCP; nesse caso, o administrador local realiza os comandos.

## Troca em duas etapas

Execute como usuário Linux `openbot`; os comandos não exigem root. Nesta VPS:

```bash
cd /srv/wuzapi-mcp
.venv/bin/python -m wuzapi_mcp.keys list \
  --file /var/lib/openbot/wuzapi/secrets/mcp-clients.json
```

### 1. Preparar

Exemplo para Composio, **a executar somente quando solicitado**:

```bash
.venv/bin/python -m wuzapi_mcp.keys rotate-prepare composio \
  --file /var/lib/openbot/wuzapi/secrets/mcp-clients.json
```

O comando gera `secrets/composio-next.key` com permissão `600` e adiciona uma
entrada de transição `composio-next` ao cadastro, com as mesmas permissões e
instâncias de `composio`. O valor não é impresso. As duas chaves ficam válidas
durante a transição. Não há vencimento automático; conclua ou cancele a troca.
Não é necessário reiniciar o MCP nem desconectar o WhatsApp.

Transfira o valor para a configuração do cliente por canal privado. No Composio,
atualize a credencial da conta conectada desse Custom MCP; não substitua pela
API Key de administração do projeto Composio. No OpenBot, atualize o campo ou
arquivo que sua configuração realmente utiliza; o caminho de exemplo não
substitui a conferência dessa configuração.

Não passe a chave como argumento de comando nem a cole em conversa, log, URL
ou commit. Identifique cópias de entrega anteriores que precisarão ser retiradas
após a conclusão. Não coloque uma cópia nova em pasta com acesso público.

### 2. Testar e concluir

Faça uma consulta sem efeitos usando a chave nova **pelo cliente migrado**.
Verificar diretamente o servidor comprova que a chave funciona; isso não
comprova que a configuração do Composio/OpenBot foi atualizada.

Depois de confirmar a migração:

```bash
.venv/bin/python -m wuzapi_mcp.keys rotate-finish composio --client-updated \
  --file /var/lib/openbot/wuzapi/secrets/mcp-clients.json
```

O comando exige a declaração `--client-updated`, confere a integridade da chave
de transição e verifica que as permissões não mudaram durante a troca. Troca
atomicamente o hash do cadastro, revoga a chave antiga, remove a entrada de
transição e promove `composio-next.key` para `composio.key`. O nome do cliente
volta a ser `composio`, preservando permissões e instâncias. A chave antiga é
rejeitada nas chamadas seguintes; não há necessidade de reiniciar o servidor.
Uma operação que já estava em andamento não é desfeita pela revogação.

Para outro cliente, substitua `composio` pelo nome cadastrado em ambos os passos.
Rotacione clientes separadamente para não interromper todos os acessos de uma vez.
Não execute `create` com permissões padrão para imitar uma rotação: o fluxo
próprio copia as restrições existentes, sem ampliar acesso.

## Cancelar

Antes da conclusão, após devolver o cliente à chave antiga se ele já foi migrado:

```bash
.venv/bin/python -m wuzapi_mcp.keys rotate-cancel composio \
  --file /var/lib/openbot/wuzapi/secrets/mcp-clients.json
```

Só a chave de transição é revogada. Se for necessário revogar o cliente por
completo, `revoke composio` também remove a transição vinculada; outro cliente
independente chamado `composio-next` não é removido por coincidência de nome.

## Interrupções e arquivos pendentes

O CLI usa um bloqueio por cadastro e troca atômica do JSON. Não existe transação
única envolvendo JSON, arquivos `.key` e configuração externa do cliente.

- Falha ao preparar pode deixar `-next.key` sem cadastro e/ou `.tmp`. A chave
  antiga permanece válida. Examine os nomes/hashes privados antes de retirar
  somente arquivos incompletos; não sobrescreva por tentativa.
- Na conclusão, o cadastro é confirmado antes de renomear `-next.key`. Se a
  renomeação falhar, a chave nova já é válida e está protegida em `-next.key`;
  a antiga já foi revogada. Rode novamente `rotate-finish ... --client-updated`
  para concluir a promoção, sem gerar outra chave. Cancelar é recusado nesse estado.
- Falha após cancelar pode deixar arquivo de entrega de uma chave já revogada;
  confirme o cadastro antes de removê-lo. Não o reutilize como credencial ativa.
- Os backups contêm o cadastro e segredos históricos. Restaurar um backup
  anterior pode reativar chaves revogadas; ao restaurar, trate explicitamente
  o cadastro atual e repita a validação das credenciais. Não publique backups.

## O que não é rotacionado

Este fluxo não altera token administrativo/por instância do WuzAPI, vínculo do
WhatsApp, HMAC de webhook, túnel Cloudflare, credenciais GitHub nem chave de
criptografia dos dados. Cada uma exige procedimento próprio. Não troque a chave
de criptografia como se fosse uma API Key descartável.

## Validação

Testes usam cadastro e chaves fictícias em diretório temporário. Cobrem
coexistência das duas chaves, conservação de escopos/instâncias, conclusão,
cancelamento, revogação completa, colisão de nome, alteração de permissões e
retomada após interrupção. Nenhum teste usa ou rotaciona as chaves da VPS.
