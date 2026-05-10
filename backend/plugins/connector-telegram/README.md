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

- Text messages (DMs and groups)
- Progressive streaming — reply is sent once, then edited as tokens arrive
- Typing indicator while Tank is thinking
- Long messages truncated to Telegram's 4096-character limit

## What doesn't work yet

- **Voice notes**: silently ignored (logged at `debug`). Voice support lands
  in a later phase.
- **Photos, documents, stickers**: silently ignored.
- **Access control**: any Telegram user who finds the bot can talk to Tank
  and drive its tools. **Deploy privately.** Per-identity allowlist is
  planned.
- **Slash commands, inline keyboards**: not handled specially; slash commands
  are passed to the LLM as plain text.

## Channel model

Each Telegram chat (DM or group) auto-creates a Tank channel with slug
`telegram-tg-chat-<chat_id>`. That channel is the single source of truth for
the conversation — accessible from the web UI, listed in `/api/channels`, and
durably persisted in SQLite. A second message from the same Telegram chat
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
