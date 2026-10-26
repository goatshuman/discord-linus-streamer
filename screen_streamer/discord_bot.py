from __future__ import annotations

import logging

import discord
from discord import app_commands

from .config import ConfigurationError, Settings
from .controller import StreamController

logger = logging.getLogger(__name__)


class StreamBot(discord.Client):
    def __init__(self) -> None:
        super().__init__(intents=discord.Intents.none())
        self.tree = app_commands.CommandTree(self)


def is_authorized(
    settings: Settings,
    *,
    user_id: int,
    guild_id: int | None,
    command_name: str,
) -> bool:
    if settings.discord_allowed_guild_ids and guild_id not in settings.discord_allowed_guild_ids:
        return False
    if user_id in settings.discord_allowed_user_ids:
        return True
    if command_name in {"start", "stop"}:
        return user_id == settings.screen1_discord_user_id
    if command_name in {"status", "share"}:
        return user_id in {
            settings.screen1_discord_user_id,
            settings.screen2_discord_user_id,
        }
    return False


def create_bot(settings: Settings, controller: StreamController) -> discord.Client:
    settings.validate_discord()
    client = StreamBot()
    tree = client.tree
    commands_synced = False

    async def require_allowed(
        interaction: discord.Interaction,
        command_name: str,
    ) -> bool:
        if is_authorized(
            settings,
            user_id=interaction.user.id,
            guild_id=interaction.guild_id,
            command_name=command_name,
        ):
            return True
        await interaction.response.send_message(
            "You do not have the configured screen1, screen2, or admin permission for this command.",
            ephemeral=True,
        )
        logger.warning(
            "Rejected Discord command from user_id=%s guild_id=%s.",
            interaction.user.id,
            interaction.guild_id,
        )
        return False

    @tree.command(name="start", description="Start screen1's Linux capture stream.")
    async def start_command(interaction: discord.Interaction) -> None:
        if not await require_allowed(interaction, "start"):
            return
        started, message = await controller.start()
        await interaction.response.send_message(message, ephemeral=True)
        logger.info("Discord start command: accepted=%s user_id=%s", started, interaction.user.id)

    @tree.command(name="stop", description="Stop screen1's Linux capture stream.")
    async def stop_command(interaction: discord.Interaction) -> None:
        if not await require_allowed(interaction, "stop"):
            return
        stopped, message = await controller.stop()
        await interaction.response.send_message(message, ephemeral=True)
        logger.info("Discord stop command: accepted=%s user_id=%s", stopped, interaction.user.id)

    @tree.command(name="status", description="Show the stream state and connection details.")
    async def status_command(interaction: discord.Interaction) -> None:
        if not await require_allowed(interaction, "status"):
            return
        status = controller.status()
        error = status["lastError"] or "None"
        await interaction.response.send_message(
            f"State: **{status['state']}** · "
            f"{status['resolution']} at {status['fps']} FPS · "
            f"{status['encoder']} · reconnects: {status['reconnectCount']}\n"
            f"Last error: {error}",
            ephemeral=True,
        )

    @tree.command(name="share", description="Post the HLS player link for screen2 to watch.")
    async def share_command(interaction: discord.Interaction) -> None:
        if not await require_allowed(interaction, "share"):
            return
        if not settings.public_view_url:
            await interaction.response.send_message(
                "Set PUBLIC_VIEW_URL in the local environment before sharing the player.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            f"Live desktop player: {settings.public_view_url}",
            ephemeral=False,
        )

    @client.event
    async def on_ready() -> None:
        nonlocal commands_synced
        if not commands_synced:
            await tree.sync()
            commands_synced = True
        logger.info("Discord bot connected as %s.", client.user)

    @tree.error
    async def on_app_command_error(
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        logger.error(
            "Discord command failed: %s",
            error,
            exc_info=(type(error), error, error.__traceback__),
        )
        message = "The command failed. Check the local streamer log for details."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    return client
