# Mensagens e formatos

## Ferramentas e payloads

Prefira `send_text`/`send_buttons` para os casos cobertos. Outros formatos usam
`api_operations` → `api_schema` → `api_call`; não envie o texto literal de um
`$ref` como corpo. Use o `path_template` e o método exatamente como descobertos.
Toda alteração via `api_call` exige `confirmed=true` com autorização prévia.
Confirme escopo `send` para envios; ter `read` ou `write` não implica `send`.

Os exemplos abaixo são modelos, não destinatários ou autorização de envio.
Substitua `ID_DA_INSTANCIA` e `TELEFONE_AUTORIZADO` por valores reais antes de chamar.

### Texto, preview e botões

Preview nativo: `send_text(instance_id=..., phone=..., text=..., link_preview=true)`.
`send_buttons` não recebe `link_preview`. Um link no corpo com botão não garante
preview nativo. Para card com imagem e botão, informe `image` como URL pública
JPEG/PNG ou data URL compatível. Na chamada à ferramenta `send_buttons`:

```json
{
  "instance_id": "ID_DA_INSTANCIA",
  "phone": "TELEFONE_AUTORIZADO",
  "text": "Confira os detalhes da oferta.",
  "buttons": [{"type": "cta_url", "title": "Ver oferta", "url": "https://example.com/oferta"}]
}
```

Evite repetir a URL visível no texto quando ela já estiver no botão. Se o usuário
pedir a URL escrita, inclua-a. Botões aceitos pelo adaptador: `reply` com `id`
opcional; `cta_url` com `url`; `cta_call` com `phone_number`; `copy` com
`copy_code`; `voice_call` experimental. Título até 20 caracteres. Prefira envelope
`original`, validado. `fork`/`viewonce` não têm validação equivalente.

`copy_code` copia texto; não cria um código. Para pareamento, obtenha antes o
valor real com `pairing_code`. Nunca use o token da API como código de acesso.

### Carrossel

Na versão validada, `/chat/send/carousel` exige conversa individual PN/LID,
corpo geral de 1–1024 caracteres e 2–10 cards. Cada card tem `Body` com
1–160 caracteres, `Image` JPEG/PNG e 1–3 `Buttons`. Tipos de botão: `reply`,
`cta_url`, `cta_call`; IDs de resposta devem ser únicos. O formato desses
botões difere de `send_buttons`; consulte o schema ativo.

Exemplo de corpo para `api_call`, após descobrir o endpoint:

```json
{
  "Phone": "TELEFONE_AUTORIZADO",
  "Body": "Escolha uma opção.",
  "Cards": [
    {"Body": "Produto A", "Image": "https://example.com/a.jpg", "Buttons": [{"type": "cta_url", "title": "Ver produto A", "url": "https://example.com/a"}]},
    {"Body": "Produto B", "Image": "https://example.com/b.jpg", "Buttons": [{"type": "cta_url", "title": "Ver produto B", "url": "https://example.com/b"}]}
  ]
}
```

Não existe `LinkPreview` por card nesse endpoint; foi rejeitado com HTTP 400
antes do envio. Montagem a partir do link: o cliente extrai Open Graph
(`og:title`, `og:description`, `og:image`), valida os dados e monta os cards.
Uma imagem retornada como WebP precisa ser convertida para JPEG/PNG. O MCP não
tem extrator/conversor dedicado: não prometa esse fluxo a um cliente sem essas
capacidades. Use o botão para o destino; sem URL redundante no corpo.
Carrossel no grupo foi rejeitado pela API; não tente contornar isso enviando
para outro destinatário sem autorização.

### Mídia e GIF

Imagem, MP3 comum, OGG/Opus como voz (`PTT=true`), MP4, PDF, GIF como documento,
sticker animado, lista e enquete tiveram envio aceito no grupo. Confira o
schema de cada endpoint. Para voz, `data:audio/ogg;base64,` funcionou;
parâmetros MIME extras na data URL causaram rejeição. O adaptador aceita JSON,
não o endpoint multipart de gravação. Limite do adaptador: corpo/resposta até
32 MiB; cada endpoint pode impor limites menores, e base64 aumenta o tamanho.

Há três apresentações distintas para animação: documento GIF para baixar,
sticker animado e GIF reproduzido em loop na conversa. O último foi confirmado
pelo titular usando MP4 H.264 sem áudio e envio raw com:

```json
{"Message": {"videoMessage": {"gifPlayback": true}}}
```

Esse fragmento **não é um payload completo**. Raw exige os dados reais da mídia
enviada ao WhatsApp: URL/directPath, mediaKey, hashes e demais campos. Não
fabrique esses campos ou exponha chaves ao usuário. O teste reutilizou, no
servidor, metadados privados de um vídeo de controle; não há ferramenta MCP
autossuficiente para converter/upload/enviar GIF em loop. Não leia bancos nem
ative histórico só para reproduzir esse caminho sem autorização apropriada.
O endpoint normal de vídeo não expõe `GifPlayback`; campo desconhecido pode
ser ignorado. Não envie novamente um controle já enviado por tentativa incerta.

## Reações, respostas, grupos e presença

- Reação via `/chat/react`: `Phone`, `Body` com emoji e `Id` real. Para mensagem
  própria, prefixo `me:`; para mensagem de outra pessoa no grupo, use também
  `Participant` com o JID do autor. `Body="remove"` remove a reação.
- Resposta citada: no schema de texto, use `ContextInfo.StanzaId` e
  `ContextInfo.Participant` reais e `QuotedText` ou `QuotedMessage`. Não invente IDs.
- Histórico depende de retenção configurada. Se desativado, obtenha os IDs por
  webhook/evento ou peça o dado faltante; não habilite armazenamento silenciosamente.
- A API criou grupo com titular administrador e outro participante comum;
  operações adicionais obedecem às permissões WhatsApp. Admin MCP não torna
  a conta administradora do grupo.
- Não existe assinatura individual mudando o cabeçalho do remetente a cada
  envio. A assinatura de atendente pode ser texto. Perfil é global.
- Disponível/indisponível, digitando/pausado e gravando/pausado foram aceitos.
  A inscrição de presença foi aceita, mas evento recebido não foi comprovado.
- Rejeitar chamada depende de CallOffer real (`call_from`, `call_id`). Nenhuma
  chamada real foi rejeitada na validação. Não use IDs fictícios como prova.

Botões URL/resposta/copiar/ligação, preview de texto, GIF em loop e cópia de
código foram confirmados pelo titular. Aceitação de outros formatos pela API
não significa validação visual em todas as versões do WhatsApp.
