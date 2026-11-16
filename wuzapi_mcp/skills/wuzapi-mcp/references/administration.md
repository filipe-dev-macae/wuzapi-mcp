# Instâncias, pareamento e configurações

## Conectar e parear

1. Consulte `list_instances` e `session(action="status")`. Reuse uma instância
   existente quando isso atender ao pedido. Não faça logout de uma conta ativa
   para testar outra opção de pareamento.
2. Se o pedido exigir nova instância, use `create_instance(name=...)` e guarde
   seu ID. O servidor gera e oculta o token WuzAPI; não crie tokens fracos nem
   peça ao usuário que os cole no chat.
3. `session(action="connect")` inicia o processo; não comprova pareamento.
   Aguarde a prontidão consultando status/QR. Consultas podem ser repetidas
   com limite curto; um envio incerto não deve ser repetido automaticamente.
4. Para código, use `pairing_code(instance_id=..., phone=...)` com DDI/DDD e
   somente dígitos. Para QR, `pairing_qr` retorna imagem MCP. Se o cliente não
   exibir a imagem, ofereça o código. Não trate o texto ocultado `[REDACTED]`
   de outras respostas como se fosse um QR válido.
5. O titular vincula o dispositivo no WhatsApp. Confirme depois `connected` e
   `loggedIn`; não considere somente o retorno de `connect`.

## Entregar código ou QR por WhatsApp

Use outra instância já conectada. A instância aguardando pareamento não pode
enviar a própria mensagem. Confirme o destinatário autorizado; não entregue
em grupo por padrão. QR/código permitem vincular uma conta e são temporários.

Para código: obtenha `LinkingCode` de `pairing_code`; use esse valor no botão
`{"type":"copy", "title":"Copiar código", "copy_code":"VALOR_REAL"}` de
`send_buttons` da instância conectada. O titular confirmou esse fluxo.
Para QR: envie a imagem real via endpoint de imagem, se o cliente conseguir
encaminhar o conteúdo binário/base64 da resposta. Nunca publique em URL aberta.

Em teste descartável autorizado, avise que o código será invalidado e exclua
somente a instância criada para o teste. Em pareamento real, preserve-a para
que o titular possa completar a vinculação. Não exclua automaticamente uma
instância cujo cadastro real o usuário solicitou.

## Alterações e exclusão

`session` distingue `disconnect` e `logout`. Logout encerra o vínculo e pode
exigir novo pareamento; requer `confirmed=true`. `delete_instance` apaga dados
permanentemente, exige `admin` e confirmação declarada. O modo
`preserve_devices` também é destrutivo; confira sua descrição antes de usar.
Criação, conexão sem pareamento, desconexão e exclusão foram exercitadas em
instâncias temporárias, preservando a conta principal.

Configurações extras são descobertas com `api_operations`/`api_schema`:

- Webhooks: `configure_webhook` configura o destino/eventos, mas este MCP não
  recebe eventos para o cliente. É necessário um receptor acessível pelo WuzAPI.
  Assinatura HMAC teve recebimento real validado. Nunca revele a chave; conferir
  a assinatura pertence ao receptor. Requisição sem assinatura foi rejeitada.
- Histórico: configuração altera armazenamento de conversas; respeite a
  política do titular e restaure configurações temporárias autorizadas.
- Proxy: use somente serviço autorizado. Configuração desativada foi testada;
  tráfego por proxy real não foi. O endpoint aceita HTTP/SOCKS5 na versão validada.
- S3: configurações desativadas foram gravadas/consultadas; upload para bucket
  real não foi validado. Não crie bucket, despesa ou credenciais por inferência.
- Recado/perfil: é alteração global da conta. Alteração autorizada do recado
  falhou no WhatsApp; valor anterior ficou intacto. Não equivale a Status de 24h.

## Escopos e diagnóstico

`read` consulta; `send` envia; `write` altera sessão/configurações; `admin`
administra globalmente e exige acesso a todas as instâncias. As restrições de
instância também são verificadas. A chave MCP é exclusiva por cliente e pode
ser revogada; nunca substitua uma chave limitada pela administrativa para
contornar uma negativa.

Em 401/403, confira conexão/chave/escopo por canal privado. Em HTTP 400,
confira schema e estado antes de corrigir. Em timeout/500 após possível envio,
preserve o ID e verifique o resultado. Nunca desabilite autenticação para depurar.
