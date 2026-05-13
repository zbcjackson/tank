# connector-discord

Talk to Tank from Discord — DMs, guild channels (public and private), and
threads. Connects via Discord's [gateway
WebSocket](https://discord.com/developers/docs/topics/gateway), so Tank
doesn't need a public HTTP endpoint.

## Setup

### 1. Create a Discord application

Head to [discord.com/developers/applications](https://discord.com/developers/applications)
and click **New Application**. Name it something like "Tank" and confirm.

### 2. Add a bot user

In the left sidebar, click **Bot → Reset Token → Yes, do it!** (the page
hides the token behind this flow). Copy the generated token — that's
your `DISCORD_BOT_TOKEN`.

### 3. Enable the Message Content intent

Still on the **Bot** page, scroll to **Privileged Gateway Intents** and
toggle **MESSAGE CONTENT INTENT** on. Without this toggle, Tank will see
message events arrive but `message.content` will be empty — the single
most common "bot doesn't respond to anything" symptom.

You do *not* need to enable the SERVER MEMBERS or PRESENCE intents
(Tank doesn't use them).

### 4. Invite the bot to a guild

Left sidebar → **Installation** (or **OAuth2 → URL Generator** on older
Developer Portal layouts). Select the `bot` scope and these permissions:

- **Send Messages**
- **Send Messages in Threads**
- **Read Message History**
- **Attach Files**
- **Embed Links**

Copy the generated URL, open it in a browser, pick the guild you want
the bot in, and confirm. DMs don't need an invite — any user can DM the
bot once it's running.

### 5. Point Tank at the bot

Export the token:

```sh
export DISCORD_BOT_TOKEN="your-bot-token-here"
```

Then add the following to `backend/core/config.yaml`:

```yaml
connectors:
  - instance: my-discord-bot
    extension: connector-discord:connector
    config:
      bot_token: ${DISCORD_BOT_TOKEN}
```

The literal `${...}` string is resolved from the environment at
startup — the token is never committed.

### 6. Start Tank

```sh
cd backend && ./scripts/dev.sh
```

Open Discord, DM the bot, type "hello". Expect a streamed reply that
edits in place as tokens arrive.

## What works in this release

- Text messages in DMs, public channels, private channels, and threads
- Progressive streaming — reply is sent once, then edited as tokens arrive
- Image attachments: inbound photos go through vision models; outbound
  `ImageBlock` replies appear as native Discord file uploads
- **Voice notes inbound**: Discord's native voice-message feature
  (2023+) uploads Opus-in-OGG; generic audio file uploads (WebM, MP3,
  M4A, WAV) are auto-transcribed via the configured ASR engine. Audio
  over 25 MB is rejected. Outbound voice (bot-sent voice messages) is
  not supported — Discord has no bot-API equivalent to `sendVoice`.
- Thread-aware replies: messaging in a thread produces a reply in that
  same thread (Tank's reply doesn't leak back to the parent channel)
- Typing indicator briefly shown while Tank is thinking
- Long messages truncated to Discord's 2000-character limit
- Per-instance allowlist — see [Access control](#access-control)
- **Admin approval** for unknown senders (`default: require_approval`
  in the allowlist): a three-button DM is sent to the admin; clicking
  swaps the View for a confirmation line.

## What doesn't work yet

- **Voice channels / Stage**: entirely separate subsystem — these are
  realtime audio rooms, not file uploads, and need a different wire
  protocol (discord.py's ``VoiceClient``). Not handled.
- **Outbound voice**: Discord's bot API can upload audio as a regular
  attachment but has no equivalent to Telegram's ``sendVoice`` that
  renders inline voice-message UI in the client. Bot-sent audio would
  land as a generic file upload.
- **Slash commands**: `/tank ask ...` isn't a first-class surface; DMs
  and channel messages only.
- **Buttons / modals / select menus**: interactive components aren't
  wired up beyond the Phase 10 approval prompt.
- **Reactions**: `on_reaction_add` isn't subscribed.
- **Thread-as-session mode**: all messages in a channel map to one Tank
  conversation regardless of which thread they belong to. You still get
  thread-local replies, but Tank's memory groups them together.
- **Rich embeds**: Tank sends plaintext; Discord's Markdown is rendered
  naturally but Tank doesn't emit Discord-specific formatting.

## Channel model

Each Discord DM auto-creates a Tank channel with slug
`discord-discord-user-<user_id>`; guild channels and threads share one
channel keyed on the *parent* channel — slug
`discord-discord-channel-<parent_channel_id>`. That channel is the
single source of truth for the conversation, accessible from the web
UI, listed in `/api/channels`, and durably persisted. Subsequent
messages from the same Discord channel resume the same conversation;
messages in a thread within that channel *also* resume that same
conversation.

## Access control

Every inbound message is checked against a per-instance allowlist
*before* any session is resolved — denied senders get a polite reply,
no Assistant is spawned, and no identity row is written.

By default (no `allowlist` key), the bot accepts messages from anyone
in any channel it's a member of and from anyone who DMs it. To lock it
down:

```yaml
connectors:
  - instance: my-discord-bot
    extension: connector-discord:connector
    config:
      bot_token: ${DISCORD_BOT_TOKEN}
      allowlist:
        default: deny
        rules:
          - external_ids: ["discord:user:123456789012345678"]
            policy: allow
            reason: "me"
          - external_ids: ["discord:channel:987654321098765432"]
            policy: allow
            reason: "engineering channel"
      unauthorized_reply: |
        Sorry, this bot is scoped to the engineering team.
```

### Identity formats

- **DMs**: `discord:user:{user_snowflake_id}`. In Discord, right-click
  your own name → **Copy User ID** (requires Developer Mode under
  **Settings → Advanced**).
- **Channels, private channels, threads**: `discord:channel:{parent_id}` —
  always the *parent text channel*, never a thread id. Right-click the
  channel → **Copy Channel ID**.

### Pattern matching

`external_ids` accepts fnmatch (shell glob) patterns. `discord:user:*`
allows any DM; `discord:channel:9*` allows channels whose ID starts
with 9. Rules are evaluated first-match-wins in the order they're
listed.

**Don't lock yourself out.** List your own `discord:user:...` in an
allow rule before switching `default` to `deny`.

### What's recorded

Every decision (allow + deny) is logged at INFO level via the
ConnectorManager. Grep the backend log for `denied inbound` to audit
rejected traffic.

## Rate limits

Discord's `chat.update` equivalent (editing a message) is roughly 5
requests per 5 seconds per channel. The connector spaces edits at
1100 ms to stay safely under the limit. If Discord still returns a
rate-limit error, the failed edit surfaces as `rate_limited:<N>` and
the next token triggers another attempt.

Messages exceeding the 2000-character cap are truncated with a trailing
ellipsis.

## Troubleshooting

**Bot connects but sees no message content (events arrive but `message.content`
is empty)**: the Message Content intent isn't enabled. Go back to
**Developer Portal → Bot → Privileged Gateway Intents** and flip
**MESSAGE CONTENT INTENT** on. Restart Tank.

**"Improper token has been passed" on startup**: the `DISCORD_BOT_TOKEN`
is wrong or was regenerated. Reset it under **Developer Portal → Bot →
Reset Token**.

**Bot is online but doesn't respond in a channel**: the bot isn't a
member of that channel, or the Send Messages permission isn't granted.
Invite the bot via the OAuth URL from step 4 with the right scopes.

**Bot replies in the wrong place after someone messages in a thread**:
expected only if the bot can't read the thread's parent channel ID.
This is normally handled automatically — report as a bug if it happens.

**"403 Forbidden" on outbound send**: the bot was kicked from the
channel, or the Send Messages permission was revoked. Check the guild's
role/permission configuration.

**Long graceful shutdown after Ctrl+C**: the gateway task drains up to
5 seconds before being cancelled. Normal.
