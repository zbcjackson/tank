"""Discord connector implementation.

Uses discord.py 2.x's gateway WebSocket (``Client.start()``). One bot
token authorises both receive and send — simpler than Slack's dual
token Socket Mode. Gateway auto-reconnect is handled by the SDK.

Supports text + image attachments in both directions. Threads are
first-class ``discord.Thread`` channels: Tank's reply goes back to the
same thread, but the underlying **session** keys on the parent channel
(matching Slack's channel-scoped model from Phase 7). Voice, slash
commands, and interactive components are out of scope for this release.

Message IDs are composite ``{channel_id}|{message_id}`` strings so the
Connector contract's single ``message_id`` can round-trip through
:meth:`edit` — both pieces are needed to identify a message on
Discord's Web API.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
from typing import TYPE_CHECKING, Any

import discord
from tank_contracts.connector import (
    Attachment,
    Connector,
    ConnectorCapabilities,
    Identity,
    MessageEvent,
    SendResult,
)
from tank_contracts.connector_sdk import (
    APPROVAL_ACTION_PREFIX,
    APPROVAL_CHOICE_ALLOW_FOREVER,
    APPROVAL_CHOICE_ALLOW_ONCE,
    APPROVAL_CHOICE_DENY,
    BackgroundTaskRunner,
    build_outcome_text,
    build_prompt_text,
    decode_action,
    encode_action,
    truncate_for_platform,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger("DiscordConnector")

# Discord's edit rate limit is roughly 5 per 5 seconds per channel (1/s
# sustained, small burst). 1100 ms gives us a safety margin without
# feeling sluggish — matches Telegram's cadence.
_DEFAULT_EDIT_INTERVAL_MS = 1100

# Hard cap on ``channel.send(content=...)`` — 2000 chars, much tighter
# than Slack's 40 000 or Telegram's 4096.
_DISCORD_MAX_MESSAGE_LENGTH = 2000

# Match the /api/upload + other-connector boundary. Discord permits much
# larger uploads in absolute terms, but bot interactions rarely benefit.
_MAX_INBOUND_IMAGE_BYTES = 25 * 1024 * 1024

# Audio shares the 25 MiB ceiling — Slack's and Telegram's voice caps
# match, keeping the three-connector story uniform. Discord's native
# voice-message feature records Opus-in-OGG; generic audio uploads
# can be WebM / MP3 / WAV / M4A — all handled by the manager's
# ``decode_any_audio`` ffmpeg-sniff path.
_MAX_INBOUND_AUDIO_BYTES = 25 * 1024 * 1024

# Timeout for the gateway task to drain cleanly on shutdown.
_SHUTDOWN_TIMEOUT_S = 5.0


# Approval-button wire format (prefix + three choice literals) lives in
# ``tank_contracts.connector_sdk.constants`` and is imported at the top.


def _encode_msg_id(channel_id: int, message_id: int) -> str:
    """Serialize ``(channel_id, message_id)`` into a single string.

    The Connector contract exposes ``message_id`` as an opaque string.
    Discord needs both pieces to address a message: snowflake IDs are
    globally unique, but :meth:`edit` resolves via
    ``channel.fetch_message(id)`` and we want to skip cross-channel
    lookups. The pipe separator avoids collisions — Discord snowflakes
    are purely numeric.
    """
    return f"{channel_id}|{message_id}"


def _decode_msg_id(msg_id: str) -> tuple[int, int]:
    """Inverse of :func:`_encode_msg_id`. Raises ``ValueError`` on
    malformed input — both halves must be present and parseable as int."""
    channel_str, sep, message_str = msg_id.partition("|")
    if not sep or not channel_str or not message_str:
        raise ValueError(f"not a discord message id: {msg_id!r}")
    try:
        return int(channel_str), int(message_str)
    except ValueError as e:
        raise ValueError(f"not a discord message id: {msg_id!r}") from e


def _classify_discord_error(exc: discord.HTTPException) -> SendResult:
    """Map a ``discord.HTTPException`` into our :class:`SendResult` shape.

    Rate-limited responses surface a ``Retry-After`` header — parse it
    into the conventional ``rate_limited:<N>`` token so the upstream
    StreamConsumer can distinguish transient from terminal failures.
    """
    status = getattr(exc, "status", None)
    if status == 429:
        retry_after: str | None = None
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None) if response else None
        if headers is not None:
            with contextlib.suppress(Exception):
                retry_after = headers.get("Retry-After") or headers.get("retry-after")
        return SendResult(
            ok=False,
            error=f"rate_limited:{retry_after}" if retry_after else "rate_limited:?",
        )
    if status == 404:
        return SendResult(ok=False, error=f"discord:not_found:{exc}")
    if status == 403:
        return SendResult(ok=False, error=f"discord:forbidden:{exc}")
    return SendResult(ok=False, error=f"discord:{status or '?'}:{exc}")


class _TankDiscordClient(discord.Client):
    """Thin :class:`discord.Client` subclass that delegates events to the
    owning :class:`DiscordConnector`.

    We subclass rather than use ``@client.event`` because subclassing is
    the idiomatic pattern when event dispatch depends on instance state
    (our connector's ``_on_message`` handler, instance-specific logging).
    """

    def __init__(
        self,
        *,
        connector: DiscordConnector,
        intents: discord.Intents,
    ) -> None:
        super().__init__(intents=intents)
        self._connector = connector

    async def on_ready(self) -> None:
        logger.info(
            "Discord connector '%s' gateway ready as %s (%d guilds)",
            self._connector.instance_name,
            self.user,
            len(self.guilds),
        )

    async def on_message(self, message: discord.Message) -> None:
        await self._connector._on_discord_message(message)  # noqa: SLF001

    async def on_interaction(self, interaction: discord.Interaction) -> None:
        """Phase 10: dispatch approval button clicks to the broker.

        Catching interactions at the client level (rather than binding
        callbacks to specific ``discord.ui.View`` instances) has one
        practical advantage: the approval prompts persist in the admin's
        DM even after Tank restarts, but the in-memory ``View`` objects
        don't. By routing on ``custom_id`` here, post-restart clicks
        reach the broker (which then no-ops on stale ``approval_id``,
        matching Telegram/Slack behaviour). discord.py fires
        :meth:`on_interaction` for *every* component interaction —
        filtering on the ``approve:`` prefix keeps us out of the way of
        any future non-approval UI.
        """
        if interaction.type is not discord.InteractionType.component:
            return
        custom_id = (interaction.data or {}).get("custom_id") or ""
        if not custom_id.startswith(f"{APPROVAL_ACTION_PREFIX}:"):
            return
        await self._connector._on_approval_interaction(  # noqa: SLF001
            interaction, custom_id,
        )


class DiscordConnector(Connector):
    """Platform adapter for Discord (gateway Socket Mode equivalent).

    One connector instance serves arbitrarily many guilds through a
    single bot token — Discord's native multi-guild model. Deploy
    multiple instances only when you want distinct bot identities.
    """

    platform = "discord"

    def __init__(
        self,
        *,
        instance_name: str,
        bot_token: str,
    ) -> None:
        super().__init__(
            instance_name=instance_name,
            capabilities=ConnectorCapabilities(
                supports_edits=True,
                edit_min_interval_ms=_DEFAULT_EDIT_INTERVAL_MS,
                max_message_length=_DISCORD_MAX_MESSAGE_LENGTH,
                supports_images_in=True,
                supports_images_out=True,
                supports_voice_in=True,
                supports_voice_out=False,
                supports_typing_indicator=True,
            ),
        )
        self._token = bot_token
        self._client: discord.Client | None = None
        # Shared lifecycle coordinator owns the drain-then-cancel dance
        # after ``stop()`` signals the gateway via ``client.close()``.
        self._runner = BackgroundTaskRunner(
            instance_name=instance_name,
            platform=self.platform,
            shutdown_timeout_s=_SHUTDOWN_TIMEOUT_S,
        )

    # ── Lifecycle ───────────────────────────────────────────────────

    async def start(self) -> None:
        if self._connected:
            return

        # ``Intents.default()`` covers guilds + guild_messages + dm_messages.
        # ``message_content`` is a *privileged* intent: operators must
        # also flip the MESSAGE CONTENT INTENT toggle in the Developer
        # Portal, or ``message.content`` will be empty for all events.
        # This is the single most common "bot sees events but can't read
        # anything" gotcha; the README covers it.
        intents = discord.Intents.default()
        intents.message_content = True

        self._client = _TankDiscordClient(connector=self, intents=intents)
        self._runner.spawn(self._run_gateway())
        self._connected = True
        logger.info("Discord connector '%s' started", self.instance_name)

    async def _run_gateway(self) -> None:
        """Run the gateway until cancelled or the client disconnects.

        Exception logging + cancellation handling now live on the
        shared :class:`BackgroundTaskRunner`; this method is a thin
        platform-specific await the runner wraps.
        """
        assert self._client is not None  # noqa: S101
        await self._client.start(self._token)

    async def stop(self) -> None:
        if not self._connected:
            return
        if self._client is not None:
            with contextlib.suppress(Exception):
                await self._client.close()
        # Shared drain-then-cancel matches the other connectors.
        await self._runner.drain()
        self._client = None
        self._connected = False
        logger.info("Discord connector '%s' stopped", self.instance_name)

    # ── Inbound ─────────────────────────────────────────────────────

    async def _on_discord_message(self, message: discord.Message) -> None:
        """Handle an inbound ``message`` event from the gateway.

        Discord's gateway delivers every message the bot can see — we
        filter out the bot's own echoes (to prevent reply loops) and
        other bots' messages (conservative default — if a user wants to
        build bot-to-bot chains, they can opt in via a future flag).

        Unlike Slack, Discord has no ``subtype`` concept; edit/delete
        events fire on *separate* event types (``on_message_edit``,
        ``on_message_delete``) we don't subscribe to. Simpler filter
        story.
        """
        if self._on_message is None:
            return
        if self._client is not None and message.author.id == self._client.user.id:  # type: ignore[union-attr]
            return
        if message.author.bot:
            return

        identity = self._make_identity(message)

        attachments: list[Attachment] = []
        for disc_att in message.attachments:
            att = await self._download_attachment(disc_att)
            if att is not None:
                attachments.append(att)

        msg_event = MessageEvent(
            identity=identity,
            text=message.content or "",
            attachments=tuple(attachments),
            reply_to_message_id=None,
            raw={
                "message_id": message.id,
                "channel_id": message.channel.id,
                "author_id": message.author.id,
            },
        )
        try:
            await self._on_message(msg_event)
        except Exception:
            logger.exception(
                "Discord connector '%s': inbound handler raised",
                self.instance_name,
            )

    def _make_identity(self, message: discord.Message) -> Identity:
        """Build an :class:`Identity` from a Discord ``message``.

        DMs (``message.guild is None``) emit ``discord:user:{user_id}``
        so allowlists can match individual people across DM restarts.
        Guild channels and threads both emit
        ``discord:channel:{parent_id}`` — i.e., a thread message
        collapses to the parent channel's session, matching Slack's
        channel-scoped semantics from Phase 7.

        :attr:`Identity.metadata` carries both the actual channel id
        (where outbound replies go) and the parent id (which identifies
        the session) so callers never need to re-derive the thread/
        parent relationship.
        """
        author = message.author
        channel = message.channel
        is_dm = message.guild is None

        if is_dm:
            external_id = f"discord:user:{author.id}"
            parent_channel_id = channel.id
            thread_id: int | None = None
        else:
            # Guild channels and threads both land here. When ``channel``
            # is a :class:`~discord.Thread`, ``channel.parent_id`` is
            # the owning text channel; we use that for the session key
            # so threads share conversation history with their parent.
            parent_channel_id = getattr(channel, "parent_id", None) or channel.id
            external_id = f"discord:channel:{parent_channel_id}"
            thread_id = (
                channel.id if parent_channel_id != channel.id else None
            )

        display_name = (
            getattr(author, "display_name", None)
            or getattr(author, "name", None)
            or str(author.id)
        )

        return Identity(
            platform=self.platform,
            external_id=external_id,
            display_name=display_name,
            is_group=not is_dm,
            metadata={
                "user_id": author.id,
                # The actual channel/thread the message lives in —
                # outbound replies go here to land in-thread when applicable.
                "channel_id": channel.id,
                # The parent text-channel id — identifies the session.
                "parent_channel_id": parent_channel_id,
                "guild_id": message.guild.id if message.guild else None,
                "thread_id": thread_id,
            },
        )

    async def _download_attachment(
        self, attachment: discord.Attachment,
    ) -> Attachment | None:
        """Fetch an inbound Discord attachment's bytes and wrap it as
        a framework :class:`Attachment`.

        Handles two inbound kinds:

        - ``image/*`` → ``Attachment(kind="image")`` for vision-capable
          LLMs (gated downstream by the model's image capability).
        - ``audio/*`` → ``Attachment(kind="audio")`` for ASR. Discord's
          native voice-message feature (2023+) uploads Opus-in-OGG;
          generic audio file uploads (WebM, MP3, M4A) are handled the
          same way. The manager's :meth:`_audio_to_text_block` routes
          the bytes through :func:`decode_any_audio`'s ffmpeg-sniff
          path for MIMEs other than ``audio/ogg``.

        Other MIME types (documents, archives, video) are dropped with
        a debug log. ``attachment.read()`` returns bytes via discord.py's
        internal HTTP session — no separate auth required because the
        attachment URLs are pre-signed.
        """
        mime_type = attachment.content_type or ""
        if mime_type.startswith("image/"):
            kind: str = "image"
            cap = _MAX_INBOUND_IMAGE_BYTES
        elif mime_type.startswith("audio/"):
            kind = "audio"
            cap = _MAX_INBOUND_AUDIO_BYTES
        else:
            logger.debug(
                "Discord connector '%s': dropping unsupported attachment "
                "mime=%s",
                self.instance_name, mime_type,
            )
            return None

        size = attachment.size or 0
        if size and size > cap:
            logger.info(
                "Discord connector '%s': dropping oversized inbound %s "
                "(%d bytes)",
                self.instance_name, kind, size,
            )
            return None

        try:
            data = await attachment.read()
        except Exception:
            logger.exception(
                "Discord connector '%s': attachment.read() raised",
                self.instance_name,
            )
            return None

        if not data:
            return None
        if len(data) > cap:
            logger.info(
                "Discord connector '%s': dropping inbound %s that "
                "exceeded cap after read (%d bytes)",
                self.instance_name, kind, len(data),
            )
            return None

        return Attachment(kind=kind, data=data, mime_type=mime_type)

    # ── Outbound ────────────────────────────────────────────────────

    async def send(
        self,
        identity: Identity,
        text: str,
        *,
        reply_to: str | None = None,  # noqa: ARG002 — reserved; Discord's reference API is different
        attachments: tuple[Attachment, ...] = (),
    ) -> SendResult:
        if self._client is None:
            return SendResult(ok=False, error="not connected")

        channel_id = identity.metadata.get("channel_id")
        if channel_id is None:
            return SendResult(
                ok=False,
                error=f"bad_identity:missing_channel_id:{identity.external_id!r}",
            )

        channel = await self._resolve_channel(channel_id, identity)
        if channel is None:
            return SendResult(ok=False, error=f"discord:channel_not_found:{channel_id}")

        image_att = next(
            (a for a in attachments if a.kind == "image"),
            None,
        )
        if image_att is not None:
            return await self._send_image(
                channel=channel,
                attachment=image_att,
                caption=text,
            )

        truncated = truncate_for_platform(text, _DISCORD_MAX_MESSAGE_LENGTH)
        try:
            msg = await channel.send(content=truncated)
        except discord.HTTPException as e:
            return _classify_discord_error(e)

        return SendResult(
            ok=True,
            message_id=_encode_msg_id(msg.channel.id, msg.id),
        )

    async def _send_image(
        self,
        *,
        channel: Any,  # discord.abc.Messageable
        attachment: Attachment,
        caption: str,
    ) -> SendResult:
        """Upload one image via ``channel.send(file=...)``.

        Bytes go through :class:`discord.File` — discord.py accepts an
        in-memory file pointer so we don't have to touch disk. URL
        payloads are fetched ourselves (Discord doesn't accept arbitrary
        remote URLs for attachments the way Telegram does).

        Image sends return no edit-addressable ``message_id`` — Discord
        allows editing the caption on a file message (``Message.edit``),
        but the StreamConsumer only edits text messages today. Matches
        the Slack behaviour.
        """
        assert self._client is not None  # noqa: S101

        if isinstance(attachment.data, bytes):
            content = attachment.data
        elif isinstance(attachment.data, str):
            # URL case — fetch and re-upload. Use discord.py's shared
            # aiohttp session via the HTTP client to avoid pulling in
            # our own dependency path.
            try:
                import aiohttp

                async with aiohttp.ClientSession() as session:
                    async with session.get(attachment.data) as resp:
                        if resp.status != 200:
                            return SendResult(
                                ok=False,
                                error=f"discord:url_fetch_failed:{resp.status}",
                            )
                        content = await resp.read()
            except Exception as e:
                return SendResult(ok=False, error=f"discord:url_fetch:{e}")
        else:
            return SendResult(
                ok=False,
                error=f"bad_attachment_data:{type(attachment.data).__name__}",
            )

        if not content:
            return SendResult(ok=False, error="empty_payload")

        send_caption: str | None = None
        if caption:
            send_caption = truncate_for_platform(caption, _DISCORD_MAX_MESSAGE_LENGTH)

        filename = attachment.filename or "image.png"
        file = discord.File(fp=io.BytesIO(content), filename=filename)

        try:
            await channel.send(content=send_caption, file=file)
        except discord.HTTPException as e:
            return _classify_discord_error(e)

        # Image sends don't expose an edit-addressable message_id —
        # intentional; StreamConsumer only edits text messages.
        return SendResult(ok=True, message_id=None)

    async def edit(
        self,
        identity: Identity,  # noqa: ARG002 — channel resolved from message_id
        message_id: str,
        text: str,
    ) -> SendResult:
        if self._client is None:
            return SendResult(ok=False, error="not connected")

        try:
            channel_id, disc_message_id = _decode_msg_id(message_id)
        except ValueError:
            return SendResult(ok=False, error=f"bad_message_id:{message_id!r}")

        channel = self._client.get_channel(channel_id)
        if channel is None:
            with contextlib.suppress(discord.HTTPException):
                channel = await self._client.fetch_channel(channel_id)
        if channel is None:
            return SendResult(ok=False, error=f"discord:channel_not_found:{channel_id}")

        try:
            target = await channel.fetch_message(disc_message_id)  # type: ignore[union-attr]
        except discord.HTTPException as e:
            return _classify_discord_error(e)

        truncated = truncate_for_platform(text, _DISCORD_MAX_MESSAGE_LENGTH)
        try:
            await target.edit(content=truncated)
        except discord.HTTPException as e:
            return _classify_discord_error(e)

        return SendResult(ok=True, message_id=message_id)

    async def send_typing(self, identity: Identity) -> None:
        """Briefly surface the "typing..." indicator in the target channel.

        Discord exposes typing as an *interval* rather than a one-shot
        event — ``channel.typing()`` is an async context manager that
        keeps the indicator lit until the block exits (max ~10s). We
        fire a short enter/exit as a cheap pulse matching Telegram's
        one-shot semantics; callers who want a sustained indicator can
        wrap longer blocks themselves in a future enhancement.
        """
        if self._client is None:
            return
        channel_id = identity.metadata.get("channel_id")
        if channel_id is None:
            return
        channel = await self._resolve_channel(channel_id, identity)
        if channel is None:
            return
        with contextlib.suppress(discord.HTTPException):
            async with channel.typing():
                # Brief await to let Discord register the indicator.
                await asyncio.sleep(0)

    # ── Approval workflow (Phase 10) ────────────────────────────────

    async def send_approval_prompt(
        self,
        *,
        admin_identity: Identity,
        approval_id: str,
        sender: Identity,
        preview: str,
    ) -> None:
        """Send an approval-prompt DM with three button components.

        The buttons live on a :class:`discord.ui.View` attached to the
        message; their ``custom_id`` fields encode
        ``approve:<choice>:<approval_id>``. Discord routes the click
        back through :meth:`_TankDiscordClient.on_interaction`, which
        filters on the ``approve:`` prefix and calls
        :meth:`_on_approval_interaction` below.

        The View is *not* registered as persistent — that would require
        stashing it across restarts. When Tank restarts, the pending
        approval entry vanishes from the in-memory broker; subsequent
        clicks land on the interaction handler, fail the broker's
        lookup, and no-op cleanly (matching the Telegram/Slack stale
        behaviour).
        """
        if self._client is None:
            return

        admin_user_id = admin_identity.metadata.get("user_id")
        if admin_user_id is None:
            # Derive from ``discord:user:{id}`` external_id — same
            # round-trip the other identity code paths use.
            _, _, raw = admin_identity.external_id.rpartition(":")
            try:
                admin_user_id = int(raw)
            except ValueError:
                logger.warning(
                    "Discord connector '%s': cannot parse admin external_id "
                    "%r",
                    self.instance_name, admin_identity.external_id,
                )
                return

        # Resolve / open the admin's DM channel. ``get_user`` hits the
        # cache; ``fetch_user`` falls back to an HTTP lookup for a user
        # that hasn't been seen in this process's gateway session.
        user = self._client.get_user(admin_user_id)
        if user is None:
            with contextlib.suppress(discord.HTTPException):
                user = await self._client.fetch_user(admin_user_id)
        if user is None:
            logger.warning(
                "Discord connector '%s': cannot resolve admin user %s",
                self.instance_name, admin_user_id,
            )
            return
        try:
            channel = await user.create_dm()
        except discord.HTTPException:
            logger.exception(
                "Discord connector '%s': failed to open admin DM",
                self.instance_name,
            )
            return

        # Shared helper renders the plain-text body; Discord wraps the
        # first line in ``**bold**`` (Markdown) for channel.send().
        prompt_body = build_prompt_text(sender, preview)
        prompt_lines = prompt_body.split("\n", 1)
        if len(prompt_lines) == 2:
            first, rest = prompt_lines
            text = f"**{first}**\n{rest}"
        else:
            text = f"**{prompt_body}**"

        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(
            label="✅ Allow once",
            style=discord.ButtonStyle.primary,
            custom_id=encode_action(APPROVAL_CHOICE_ALLOW_ONCE, approval_id),
        ))
        view.add_item(discord.ui.Button(
            label="🔓 Allow forever",
            style=discord.ButtonStyle.success,
            custom_id=encode_action(APPROVAL_CHOICE_ALLOW_FOREVER, approval_id),
        ))
        view.add_item(discord.ui.Button(
            label="🚫 Deny",
            style=discord.ButtonStyle.danger,
            custom_id=encode_action(APPROVAL_CHOICE_DENY, approval_id),
        ))

        try:
            await channel.send(content=text, view=view)
        except discord.HTTPException:
            logger.exception(
                "Discord connector '%s': failed to send approval prompt",
                self.instance_name,
            )

    async def _on_approval_interaction(
        self,
        interaction: discord.Interaction,
        custom_id: str,
    ) -> None:
        """Route an approval button click to the :class:`ApprovalBroker`.

        Discord requires an :meth:`~discord.InteractionResponse.defer`
        (or equivalent) within 3 seconds, same as Slack. We defer first,
        then run the broker work afterwards — the broker's DB write + reply
        send can safely run past the ack window.
        """
        # Ack first — Discord shows "This interaction failed" after 3s.
        with contextlib.suppress(discord.HTTPException):
            await interaction.response.defer()

        broker = getattr(self, "_broker", None)
        if broker is None:
            logger.debug(
                "Discord connector '%s': approval interaction arrived but "
                "no broker is attached; ignoring",
                self.instance_name,
            )
            return

        decoded = decode_action(custom_id)
        if decoded is None:
            logger.debug(
                "Discord connector '%s': ignoring unrecognised custom_id %r",
                self.instance_name, custom_id,
            )
            return
        choice, approval_id = decoded

        clicker = interaction.user
        if clicker is None:
            logger.warning(
                "Discord connector '%s': approval interaction without user",
                self.instance_name,
            )
            return
        clicker_identity = Identity(
            platform=self.platform,
            external_id=f"discord:user:{clicker.id}",
            display_name=(
                getattr(clicker, "display_name", None)
                or getattr(clicker, "name", None)
                or str(clicker.id)
            ),
            is_group=False,
            metadata={"user_id": clicker.id},
        )

        try:
            resolved = await broker.resolve(
                approval_id, choice, clicker_identity,
            )
        except Exception:
            logger.exception(
                "Discord connector '%s': broker.resolve raised",
                self.instance_name,
            )
            return

        # Edit the prompt message to swap the View (three buttons) for
        # a single outcome line. Without this the buttons sit there
        # looking still-clickable. ``resolved is None`` means the broker
        # no-op'd (stale click, wrong admin, unknown approval_id) —
        # leave the prompt alone so the real admin can still act.
        if resolved is None:
            return

        prompt_message = getattr(interaction, "message", None)
        if prompt_message is None:
            # Discord occasionally delivers component interactions with
            # no ``message`` (e.g. ephemeral responses). Nothing to
            # edit; broker work already landed.
            return

        outcome = build_outcome_text(
            sender=resolved.event.identity,
            choice=choice,
            admin=clicker_identity,
        )
        # ``view=None`` strips the attached View so the three buttons
        # vanish entirely; ``content`` replaces the prompt body.
        with contextlib.suppress(discord.HTTPException):
            await prompt_message.edit(content=outcome, view=None)

    # ── Helpers ────────────────────────────────────────────────────

    async def _resolve_channel(
        self, channel_id: int, identity: Identity,
    ) -> Any | None:
        """Resolve a ``channel_id`` to a ``discord.abc.Messageable``.

        Tries the gateway cache first, then falls back to ``fetch_channel``
        for guild channels/threads. DM channels sometimes miss the cache
        across reconnects — in that case we re-open the DM via
        ``user.create_dm()`` (idempotent per discord.py's API).
        """
        assert self._client is not None  # noqa: S101

        channel = self._client.get_channel(channel_id)
        if channel is not None:
            return channel

        # Guild channels / threads → HTTP fetch is cheap and documented.
        with contextlib.suppress(discord.HTTPException):
            channel = await self._client.fetch_channel(channel_id)
        if channel is not None:
            return channel

        # DM fallback: re-open via the user, using the ``user_id`` that
        # _make_identity stashed in metadata. Skips the (empty) guild
        # channel cache lookup entirely.
        user_id = identity.metadata.get("user_id")
        if user_id is None:
            return None
        user = self._client.get_user(user_id)
        if user is None:
            with contextlib.suppress(discord.HTTPException):
                user = await self._client.fetch_user(user_id)
        if user is None:
            return None
        with contextlib.suppress(discord.HTTPException):
            return await user.create_dm()
        return None

    # (Phase 11: ``_truncate`` moved to
    # ``tank_contracts.connector_sdk.truncate_for_platform`` — import at top.)
