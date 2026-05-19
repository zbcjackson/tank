# connector-wechat

WeChat connector plugin for Tank Voice Assistant. Connects to personal WeChat accounts via Tencent's iLink Bot API.

## Features

- **Long-poll transport** — no public endpoint, webhook, or WebSocket needed
- **QR code login** — scan-to-connect setup via CLI
- **DM messaging** — configurable access policies
- **Group messaging** — configurable policy (disabled by default; iLink bot identities typically cannot receive group messages)
- **Media support** — images, video, files, and voice messages
- **AES-128-ECB encrypted CDN** — automatic encryption/decryption for all media transfers
- **Context token persistence** — disk-backed reply continuity across restarts
- **Markdown formatting** — preserves Markdown in outbound messages
- **Smart message chunking** — oversized payloads split at logical boundaries
- **Typing indicators** — shows typing status while the agent processes
- **SSRF protection** — outbound media URLs are validated before download
- **Message deduplication** — 5-minute sliding window prevents double-processing

## Setup

### 1. QR Code Login

```bash
cd backend/plugins/connector-wechat
uv run python -m connector_wechat.login
```

Scan the QR code with WeChat mobile, then confirm login on your phone. Credentials are saved automatically.

### 2. Configure

Add to `backend/core/config.yaml`:

```yaml
connectors:
  - instance: my-wechat
    extension: connector-wechat:connector
    config:
      account_id: ${WECHAT_ACCOUNT_ID}
      token: ${WECHAT_TOKEN}
```

Set environment variables in `backend/.env`:

```bash
WECHAT_ACCOUNT_ID=your-account-id
WECHAT_TOKEN=your-bot-token
```

### 3. Start Tank

```bash
cd backend
uv run tank-backend
```

## Configuration Options

| Key | Default | Description |
|-----|---------|-------------|
| `account_id` | — | iLink Bot account ID (required) |
| `token` | — | iLink Bot token (required) |
| `base_url` | `https://ilinkai.weixin.qq.com` | iLink API base URL |
| `cdn_base_url` | `https://novac2c.cdn.weixin.qq.com/c2c` | CDN base URL for media |
| `group_policy` | `disabled` | Group access: `open`, `allowlist`, `disabled` |
| `group_allowlist` | `[]` | Group IDs allowed (when group_policy=allowlist) |
| `voice_in` | `true` | Accept inbound voice messages |
| `voice_out` | `true` | Send voice messages |
| `state_dir` | `~/.tank/wechat/<instance>/` | State directory |

## Identity Format

- DMs: `wechat:user:{peer_id}`
- Groups: `wechat:group:{group_id}`

## Limitations

- **No message editing** — iLink API does not support editing sent messages
- **Group messaging unreliable** — iLink bot identities typically cannot receive ordinary WeChat group messages
- **Session expiry** — tokens expire after inactivity; re-run QR login to refresh
- **Single instance per token** — only one gateway can use a given token at a time
