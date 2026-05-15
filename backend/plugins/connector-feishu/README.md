# Feishu / Lark connector

Talk to Tank from Feishu (and its international cousin Lark) over a
WebSocket long-connection. No public HTTPS endpoint needed — same shape
as the Slack Socket Mode connector.

## Setup

1. **Create a self-built app** in the [Feishu open-platform console](https://open.feishu.cn/app)
   (or [Lark](https://open.larksuite.com/app) for the international
   tenant). Pick "Custom app" / "Self-built app".

2. **Enable bot capability** under "Add features" → "Bot". Without this
   the bot can't receive messages even with the right scopes.

3. **Subscribe to events** under "Events & Callbacks" → "Add events":
   - `im.message.receive_v1` (Receive Message v2.0)
   - Optionally `im.message.message_read_v1` if you want read receipts later
   Pick **Long Connection** as the delivery mode (the SDK's `lark.ws.Client`
   path Tank uses). No webhook URL needed.

4. **Add scopes** under "Permissions & Scopes":
   - `im:message` (read+write messages on behalf of the app)
   - `im:resource` (download user-uploaded files like voice/image)
   - `im:chat` (read chat metadata)
   - `contact:user.id:readonly` (resolve display names for inbound msgs)

5. **Publish the app version** for your tenant — bots can't message
   users until at least one version is approved.

6. **Copy `App ID` + `App Secret`** from "Credentials & Basic Info" and
   point Tank at them via env vars (see config below).

## Configuration

```yaml
connectors:
  feishu:
    instances:
      my-feishu-bot:
        app_id: ${FEISHU_APP_ID}
        app_secret: ${FEISHU_APP_SECRET}
```

DMs work without any allowlist. To accept group messages or restrict
who can talk to the bot, see [Access control](#access-control).

## What works in this release

- Text messages in DMs and groups (`p2p` and `group` chat types)
- Progressive streaming — reply is sent once, then edited as tokens arrive
- Voice notes inbound: Feishu's `audio` msg_type is auto-transcribed
  via the configured ASR engine. Voice notes over 25 MB are rejected.
- Image attachments: inbound photos go through vision models; outbound
  `ImageBlock` replies appear as native Feishu image messages
- Long messages truncated to Feishu's 30 000-character limit
- Per-instance allowlist — see [Access control](#access-control)
- **Admin approval** for unknown senders (`default: require_approval`):
  three-button interactive card sent to the admin; clicking swaps the
  card for a confirmation line.

## What doesn't work yet

- **Outbound voice**: Feishu's audio messages need an upload via
  `/im/v1/files` followed by a `file_key` reference; bot-sent audio
  isn't wired here.
- **Slash commands / mentions**: bots can be `@`-mentioned in groups,
  but Tank doesn't strip the mention token from the inbound text or
  filter on it.
- **Threading**: replies always go to the parent chat; thread-as-session
  routing is deferred.
- **Rich cards**: Tank sends plaintext; Feishu's interactive cards are
  used only for the approval prompt (see Phase 10) and not for general
  output formatting.

## Access control

Same allowlist + REQUIRE_APPROVAL machinery as Telegram/Slack/Discord.
Identities are `feishu:user:<open_id>` for individuals and
`feishu:chat:<open_chat_id>` for groups. To find an open_id, send a
message and grep the backend log for the `feishu connector '...'
inbound from feishu:user:...` line — the receiver can also share their
own ID via `/api/whoami` once the bot is talking.

## Channel model

Each Feishu DM auto-creates a Tank channel with slug
`feishu-feishu-user-<open_id>`; group chats use
`feishu-feishu-chat-<open_chat_id>`. That channel is the single source
of truth — accessible from the web UI, listed in `/api/channels`, and
durably persisted. Subsequent messages from the same Feishu chat
resume the same conversation.

## Rate limits

Feishu's send-message rate limit is roughly 50/min per app. Tank's
edit cadence (default 1100 ms) keeps streaming replies safely under
that.

## Troubleshooting

- **Bot connects but never receives messages**: check that you
  subscribed to `im.message.receive_v1` *and* picked Long Connection
  delivery. HTTP webhook delivery isn't supported by this connector.
- **400 on send**: check that `Bot` capability is enabled and the
  app version is published. Newly created bots without published
  versions can connect over WebSocket but can't send.
- **Unknown identities**: the open_id format depends on whether the
  app is internal (`ou_*`) or ISV (different prefix). Tank treats both
  as opaque strings; the prefix doesn't affect routing.
