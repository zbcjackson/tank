# connector-slack

Talk to Tank from Slack — DMs, channels, private groups, and multi-person
DMs (MPIMs). Connects via [Socket Mode](https://api.slack.com/apis/socket-mode)
so Tank doesn't need a public HTTP endpoint.

## Setup

### 1. Create a Slack app

Head to [api.slack.com/apps](https://api.slack.com/apps) and click **Create New
App → From scratch**. Name it something like "Tank", pick a workspace, and
continue.

### 2. Enable Socket Mode

On the app settings page, go to **Socket Mode → Enable Socket Mode**. When it
prompts for an app-level token name, call it "tank-socket" (or anything else),
and copy the generated `xapp-...` token. That's your `SLACK_APP_TOKEN`.

### 3. Add bot scopes

Under **OAuth & Permissions → Scopes → Bot Token Scopes**, add the scopes Tank
needs to receive and reply:

- `app_mentions:read`
- `channels:history`
- `groups:history`
- `im:history`
- `mpim:history`
- `chat:write`
- `files:read`
- `files:write`
- `users:read`

### 4. Subscribe to message events

Under **Event Subscriptions → Enable Events**, toggle on. Add the following
bot events:

- `message.channels`
- `message.groups`
- `message.im`
- `message.mpim`

Save changes. Socket Mode apps don't need a Request URL — the subscriptions are
delivered over the WebSocket.

### 5. Install to workspace

Under **OAuth & Permissions**, click **Install to Workspace**. Slack will ask
you to confirm the scopes. After install, copy the **Bot User OAuth Token**
(`xoxb-...`). That's your `SLACK_BOT_TOKEN`.

### 6. Point Tank at the bot

Export both tokens:

```sh
export SLACK_BOT_TOKEN="xoxb-..."
export SLACK_APP_TOKEN="xapp-..."
```

Then add the following to `backend/core/config.yaml`:

```yaml
connectors:
  - instance: my-slack-bot
    extension: connector-slack:connector
    config:
      bot_token: ${SLACK_BOT_TOKEN}
      app_token: ${SLACK_APP_TOKEN}
```

The literal `${...}` strings are resolved from the environment at startup — the
tokens are never committed.

### 7. Start Tank + invite the bot

```sh
cd backend && ./scripts/dev.sh
```

For channels (public or private), type `/invite @YourBotName` in the channel.
DMs work without invitation — just open a DM with the bot.

## What works in this release

- Text messages in DMs, public channels, private channels, and MPIMs
- Progressive streaming — reply is sent once, then edited as tokens arrive
- Image attachments: inbound photos go through vision models; outbound
  `ImageBlock` replies appear as native Slack file uploads
- Thread-aware replies: if you message in a thread, Tank replies in that same
  thread
- Long messages truncated to Slack's 40 000-character limit
- Per-instance allowlist — see [Access control](#access-control)

## What doesn't work yet

- **Voice notes**: Slack's audio files aren't handled (the voice flow that
  Telegram supports is deferred for Slack)
- **Slash commands**: `/ask-tank ...` isn't a first-class surface; mention-only
  / DM-only for now
- **Interactive components** (buttons, modals, shortcuts): none
- **Ephemeral replies** (`chat.postEphemeral`): not exposed
- **Thread-as-session**: all messages in a channel map to one Tank conversation
  regardless of which thread they belong to. You'll still get thread-local
  replies, but Tank's memory groups them together
- **Rich block formatting**: Tank sends plaintext; Slack's markdown is
  respected on the wire but Tank doesn't emit Slack-specific formatting

## Channel model

Each Slack DM auto-creates a Tank channel with slug `slack-slack-user-<U>`;
channels/groups/MPIMs use `slack-slack-channel-<C>`. That channel is the
single source of truth for the conversation — accessible from the web UI,
listed in `/api/channels`, and durably persisted. Subsequent messages from
the same Slack channel resume the same conversation.

## Access control

Every inbound message is checked against a per-instance allowlist *before*
any session is resolved — denied senders get a polite reply, no Assistant is
spawned, and no identity row is written.

By default (no `allowlist` key), the bot accepts messages from anyone in any
channel it's a member of. To lock it down:

```yaml
connectors:
  - instance: my-slack-bot
    extension: connector-slack:connector
    config:
      bot_token: ${SLACK_BOT_TOKEN}
      app_token: ${SLACK_APP_TOKEN}
      allowlist:
        default: deny
        rules:
          - external_ids: ["slack:user:U01ABCDEF"]
            policy: allow
            reason: "me"
          - external_ids: ["slack:channel:C01TEAMCHAN"]
            policy: allow
            reason: "engineering channel"
      unauthorized_reply: |
        Sorry, this bot is scoped to the engineering team.
```

### Identity formats

- **DMs**: `slack:user:{U01ABCDEF}`. Find yours by clicking your own name in
  Slack → **Copy member ID**.
- **Channels / groups / MPIMs**: `slack:channel:{C01EXAMPLE}`. Right-click
  the channel name → **Copy link** — the ID is the last path segment.

### Pattern matching

`external_ids` accepts fnmatch (shell glob) patterns. `slack:user:*` allows
any DM; `slack:channel:C*` allows every public channel. Rules are evaluated
first-match-wins in the order they're listed.

**Don't lock yourself out.** List your own `slack:user:...` in an allow rule
before switching `default` to `deny`.

### What's recorded

Every decision (allow + deny) is logged at INFO level via the ConnectorManager.
Grep the backend log for `denied inbound` to audit rejected traffic.

## Rate limits

Slack's `chat.update` is Tier 3, roughly 50 requests per minute per workspace.
The connector spaces edits at 1400 ms to stay safely under the limit. If Slack
still returns a rate-limit error (rare, but possible under cross-chat load),
the failed edit is surfaced as `rate_limited:<N>` and the next token triggers
another attempt.

Messages that exceed the 40 000-character cap are truncated with a trailing
ellipsis.

## Troubleshooting

**"invalid_auth" on startup**: the `SLACK_BOT_TOKEN` is wrong, expired, or
doesn't belong to this workspace. Reinstall the app via **OAuth & Permissions
→ Install to Workspace**.

**"not_allowed_token_type"**: the two tokens are swapped. `SLACK_BOT_TOKEN`
must start with `xoxb-`; `SLACK_APP_TOKEN` must start with `xapp-`.

**Bot doesn't reply in a channel**: the bot isn't invited. `/invite @YourBotName`
in the channel. Slack silently drops events for non-member bots.

**Event arrives but no reply lands**: check `tmux capture-pane -t tank -p -S
-200` — usually this is a pre-existing Tank error (LLM misconfigured, DB
unreachable, token expired), not a Slack-side issue.

**Messages in threads get main-channel replies**: expected only if the bot
misses the `thread_ts` on the inbound event. This is normally handled
automatically; report as a bug if it happens.

**"channel_not_found" on outbound send**: the bot lost access to the channel
(was kicked, or the channel was archived). Log shows the full Slack error
code.
