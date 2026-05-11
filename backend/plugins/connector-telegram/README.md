# connector-telegram

Talk to Tank from Telegram — DMs and groups.

## Setup

### 1. Create a bot

Open Telegram and talk to [@BotFather](https://t.me/BotFather):

```
/newbot
<name>    → "My Tank Bot"
<handle>  → "my_tank_bot"
```

BotFather replies with an HTTP API token of the form `123456:AAH...`.
Save it — that's the only credential.

### 2. Point Tank at the bot

Export the token as an environment variable:

```sh
export TELEGRAM_BOT_TOKEN="123456:AAH..."
```

Then add the following to `backend/core/config.yaml`:

```yaml
connectors:
  - instance: my-telegram-bot
    extension: connector-telegram:connector
    config:
      bot_token: ${TELEGRAM_BOT_TOKEN}
```

The literal `${TELEGRAM_BOT_TOKEN}` string is resolved from the environment at
startup — the token is never committed to the repo.

### 3. Start Tank

```sh
cd backend && ./scripts/dev.sh
```

Message the bot on Telegram. Tank replies with the LLM response, progressively
edited as tokens stream in.

## What works in this release

- Text messages (DMs and groups), streaming replies via progressive edits
- Photos in and out (see `supports_images_*` capability flags)
- Voice notes in and out (requires ASR + TTS engines configured on Tank)
- Typing indicator while Tank is thinking
- Long messages truncated to Telegram's 4096-character limit
- Per-instance allowlist — see [Access control](#access-control)

## What doesn't work yet

- **Documents, stickers, video notes**: silently ignored
- **Slash commands, inline keyboards**: not handled specially; slash commands
  are passed to the LLM as plain text

## Access control

Every inbound message is checked against a per-instance allowlist
*before* any session is resolved — denied senders get a polite "not
authorised" reply, no Assistant is spawned, no identity row written to
the database.

By default (no `allowlist` key in config) the bot is open. To lock it
down, add a block like this to the connector's `config`:

```yaml
connectors:
  - instance: my-telegram-bot
    extension: connector-telegram:connector
    config:
      bot_token: ${TELEGRAM_BOT_TOKEN}
      allowlist:
        default: deny              # "allow" (default) or "deny"
        rules:
          - external_ids: ["tg:user:123456789", "tg:user:987654321"]
            policy: allow
            reason: "team members"
          - external_ids: ["tg:chat:-1001234567"]
            policy: allow
            reason: "engineering group chat"
      unauthorized_reply: |        # optional; defaults to "You're not authorised to use this bot."
        Sorry, this bot is invite-only. Ask Alice for access.
```

### Identity formats

- **DMs**: `tg:user:{your Telegram user id}`. Find yours by messaging
  [@userinfobot](https://t.me/userinfobot).
- **Groups / supergroups / channels**: `tg:chat:{chat id}` — always a
  negative integer for groups. Add the bot to the chat and check the
  Tank log: every inbound message prints the identity.

### Pattern matching

`external_ids` accepts fnmatch (shell glob) patterns — so `tg:user:*`
allows any DM, `tg:chat:-100*` allows any supergroup. Rules are
evaluated first-match-wins in the order they're listed; a specific
allow above a broad deny expresses exceptions.

**Don't lock yourself out.** List your own `tg:user:{id}` in an allow
rule before switching `default` to `deny`. If you do lock yourself
out, the unauthorized reply tells you so — you'll know why your
messages aren't getting through.

### What's recorded

Every decision (allow + deny) is logged at INFO level via the
ConnectorManager. Operators can grep the backend log for `denied
inbound` to audit traffic.

## Channel model

Each Telegram DM auto-creates a Tank channel with slug
`telegram-tg-user-<user_id>`; groups use `telegram-tg-chat-<chat_id>`.
That channel is the single source of truth for the conversation —
accessible from the web UI, listed in `/api/channels`, and durably
persisted in SQLite. A second message from the same Telegram chat
resumes the same conversation.

Different chats (different DMs, or different groups) get separate sessions.

## Rate limits

Telegram caps message edits at roughly one per second per chat. The connector
spaces edits at 1100 ms to stay safely under the limit. If Telegram still
returns `TelegramRetryAfter` (rare, but possible under cross-chat load), the
failed edit is logged and the next token triggers another attempt.

## Troubleshooting

**"Unauthorized" on startup**: the token is wrong or the env var isn't
exported in the shell that launched Tank.

**Bot doesn't reply**: check `tmux capture-pane -t tank -p -S -200`. Most
commonly it's a pre-existing Tank error (LLM misconfigured, DB unreachable),
not a Telegram-side issue.

**Messages arrive but Tank seems stuck**: Telegram long-poll holds a 30-second
HTTP request. Graceful shutdown can take up to 5 seconds after the last poll
completes — that's normal.
