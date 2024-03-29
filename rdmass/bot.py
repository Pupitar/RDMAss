import arrow
import discord
import httpx
from apscheduler.jobstores.base import JobLookupError
from discord_slash import SlashCommand, ComponentContext
from discord_slash.model import ButtonStyle, SlashMessage
from discord_slash.utils import manage_components
from sentry_sdk import capture_exception
from typing import Optional, List, Text

from rdmass.config import permissions, config, scheduler
from rdmass.rdm import RDMSetApi, RDMGetApi
from rdmass.utils import (
    handle_bot_list,
    get_status_message,
    handle_dt_picker,
    handle_assignment_group,
    scheduler_migration,
    handle_clean,
    handle_auto_events,
)

client = discord.Client(intents=discord.Intents.all())
slash = SlashCommand(client, sync_commands=True)

status_refresh_component = manage_components.create_actionrow(
    *[manage_components.create_button(custom_id="status_refresh", style=ButtonStyle.blue, label="Refresh")]
)


@client.event
async def on_ready() -> None:
    print("RDMAss ready to shine!")

    if not scheduler.running:
        scheduler.start()
        scheduler_migration()

        if config.auto_event.enabled:
            if config.auto_event.check_every < 1 or config.auto_event.check_every > 60:
                return log.error("handle_events failed - set check_every to value between 1, 60")

            await sched_handle_events()
            scheduler.add_job(
                id="handle_events",
                name="events_cron",
                func=sched_handle_events,
                trigger="cron",
                minute=f"*/{config.auto_event.check_every}",
                max_instances=1,
                replace_existing=True,
            )


@client.event
async def on_component(ctx: ComponentContext) -> None:
    if ctx.custom_id == "status_refresh":
        status_ctx = await manage_components.wait_for_component(client, components=[status_refresh_component])
        await status_ctx.edit_origin(content=await get_status_message(), components=[status_refresh_component])


@client.event
async def sched_assignment_group(assignments_groups: List[Text], action: Text) -> None:
    success = await handle_assignment_group(assignments_groups, action)

    # handle tech message
    if config.instance.discord.tech_channel:
        tech_channel = await client.fetch_channel(config.instance.discord.tech_channel)

        output_message = (
            config.message.tech_channel_message_success if success else config.message.tech_channel_message_fail
        ).format(
            **{
                "action": action,
                "type": "Scheduled",
                "assignments_groups": ", ".join(assignments_groups),
            }
        )

        await tech_channel.send(output_message)

    # handle users message
    if success and config.instance.discord.user_channel:
        user_channel = await client.fetch_channel(config.instance.discord.user_channel)

        output_message = (
            config.message.user_channel_message_request
            if action == "request"
            else config.message.user_channel_message_start
        ).format(
            **{
                "action": action,
                "type": "Scheduled",
                "assignments_groups": ", ".join(assignments_groups),
            }
        )

        await user_channel.send(output_message)


@client.event
async def sched_handle_events() -> None:
    return await handle_auto_events(client, sched_assignment_group)


@client.event
async def sched_clean() -> None:
    success = await handle_clean()

    # handle tech message
    if config.instance.discord.tech_channel:
        tech_channel = await client.fetch_channel(config.instance.discord.tech_channel)

        output_message = (
            config.message.tech_channel_message_clean_success
            if success
            else config.message.tech_channel_message_clean_fail
        )

        await tech_channel.send(output_message)

    # handle users message
    if success and config.instance.discord.user_channel:
        user_channel = await client.fetch_channel(config.instance.discord.user_channel)

        await user_channel.send(config.message.user_channel_message_clean)


@slash.slash(name="rdm-jobs", guild_ids=[config.instance.discord.guild_id], permissions=permissions)
async def rdm_jobs(ctx: ComponentContext) -> Optional[SlashMessage]:
    jobs = scheduler.get_jobs()
    job_names = {job.id: job.name for job in jobs}

    jobs = [
        {
            "label": job.name,
            "value": job.id,
            "description": arrow.get(job.next_run_time)
            .to(config.locale.timezone)
            .format(f"{config.locale.datetime_format}"),
        }
        for job in jobs
        if job.id != "handle_events"
    ]

    if not jobs:
        return await ctx.send("No jobs scheduled.", hidden=config.bot.hide_bot_message)

    job_list_ctx, selected_jobs = await handle_bot_list(
        client, ctx, jobs, "Select jobs to remove", placeholder="...", custom_id="jobs_list"
    )

    if not selected_jobs:
        return await job_list_ctx.edit_origin(content=f"Aborted.", components=None)

    for job_id in selected_jobs:
        try:
            scheduler.remove_job(job_id)
        except JobLookupError:
            pass

    jobs_string = "\n".join([f"**- {job_names[job_id]}**" for job_id in selected_jobs])
    await job_list_ctx.edit_origin(content=f"Removed scheduled jobs:\n{jobs_string}", components=None)


@slash.slash(
    name="rdm-status",
    description="RDM Status",
    guild_ids=[config.instance.discord.guild_id],
    permissions=permissions,
)
async def rdm_status(ctx: ComponentContext) -> None:
    await ctx.send(
        content=await get_status_message(), components=[status_refresh_component], hidden=config.bot.hide_bot_message
    )


# noinspection PyUnboundLocalVariable
@slash.slash(
    name="rdm-reload",
    description="RDM Reload All Instances",
    guild_ids=[config.instance.discord.guild_id],
    permissions=permissions,
)
async def rdm_reload(ctx: ComponentContext) -> None:
    try:
        status = await RDMSetApi.reload_instances()
    except httpx.RequestError as e:
        capture_exception(e)
        message = f"Instances reload failed!\nError: {e}"
    else:
        message = f"Instances {'reloaded!' if status else 'reload failed!'}"
    finally:
        await ctx.send(message, hidden=config.bot.hide_bot_message)


# noinspection PyUnboundLocalVariable
@slash.slash(
    name="rdm-clear",
    description="RDM Clear All Quests",
    guild_ids=[config.instance.discord.guild_id],
    permissions=permissions,
)
async def rdm_clear(ctx: ComponentContext) -> None:
    cancel_button = manage_components.create_button(custom_id="cancel", style=ButtonStyle.gray, label="Cancel")
    action_type = manage_components.create_actionrow(
        *[
            manage_components.create_button(custom_id="schedule", style=ButtonStyle.blue, label="Schedule"),
            manage_components.create_button(custom_id="instant", style=ButtonStyle.blue, label="Instant"),
            cancel_button,
        ]
    )

    await ctx.send("Select clean type", components=[action_type], hidden=config.bot.hide_bot_message)

    action_type_ctx = await manage_components.wait_for_component(client, components=[action_type])
    action = action_type_ctx.custom_id

    if action == "cancel":
        return await action_type_ctx.edit_origin(content="Aborted.", components=None)

    elif action == "instant":
        try:
            status = await RDMSetApi.clear_all_quests()
        except httpx.RequestError as e:
            capture_exception(e)
            message = f"Quests cleanup failed!\nError: {type(e).__name__}: {e}"
        else:
            message = f"Quests {'cleaned!' if status else 'cleanup failed!'}"
        finally:
            await action_type_ctx.edit_origin(content=message, components=None, hidden=config.bot.hide_bot_message)

    else:
        hours_ctx, arrow_dt_utc, arrow_dt = await handle_dt_picker(client, action_type_ctx)
        scheduler_name = f"Clean Quests"
        scheduler.add_job(
            func=sched_clean,
            trigger="date",
            run_date=arrow_dt_utc.datetime,
            name=scheduler_name,
        )

        dt_format = f"{config.locale.datetime_format}"
        await hours_ctx.edit_origin(
            content=f"New job **{scheduler_name}** added. Will be fired at **{arrow_dt.format(dt_format)}**",
            components=None,
        )


@slash.slash(
    name="rdm-assignment-group",
    description="RDM Assignment Group",
    guild_ids=[config.instance.discord.guild_id],
    permissions=permissions,
)
async def rdm_assignment_group(ctx: ComponentContext) -> Optional[SlashMessage]:
    await ctx.defer(hidden=config.bot.hide_bot_message)

    assignment_groups = [
        {
            "label": row["name"],
            "value": row["name"],
            "description": row["assignments"][:100],
        }
        for row in await RDMGetApi.get_assignment_groups()
    ]

    if not assignment_groups:
        return await ctx.send("There's no assignment groups in this RDM instance.", hidden=config.bot.hide_bot_message)

    assignment_group_ctx, selected_assignments = await handle_bot_list(
        client,
        ctx,
        assignment_groups,
        "Select assignment groups",
        placeholder="...",
        custom_id="assignment_groups",
    )

    if not selected_assignments:
        return await assignment_group_ctx.edit_origin(
            content="Aborted.",
            components=None,
        )

    iv_only = all(x in config.instance.rdm.get("iv_only_instances", []) for x in selected_assignments)
    quest_only = all(x in config.instance.rdm.get("quest_only_instances", []) for x in selected_assignments)

    cancel_button = manage_components.create_button(custom_id="cancel", style=ButtonStyle.gray, label="Cancel")
    action_row = manage_components.create_actionrow(
        *[
            manage_components.create_button(custom_id="start", style=ButtonStyle.green, label="Start"),
            manage_components.create_button(custom_id="request", style=ButtonStyle.blue, label="ReQuest"),
            cancel_button,
        ]
    )
    action_type = manage_components.create_actionrow(
        *[
            manage_components.create_button(custom_id="schedule", style=ButtonStyle.blue, label="Schedule"),
            manage_components.create_button(custom_id="instant", style=ButtonStyle.blue, label="Instant"),
            cancel_button,
        ]
    )

    output_message = f"Target groups: {', '.join(selected_assignments)}"

    if not iv_only and not quest_only:
        await assignment_group_ctx.edit_origin(
            content=output_message,
            components=[action_row],
        )
        action_row_ctx = await manage_components.wait_for_component(client, components=[action_row])
        action = action_row_ctx.custom_id
    else:
        action = "start" if iv_only else "request"
        action_row_ctx = assignment_group_ctx

    if action == "cancel":
        return await action_row_ctx.edit_origin(content="Aborted.", components=None)

    output_message = output_message + f" Action: {action}"
    await action_row_ctx.edit_origin(
        content=output_message,
        components=[action_type],
    )
    action_type_ctx = await manage_components.wait_for_component(client, components=[action_type])

    if action_type_ctx.custom_id == "cancel":
        return await action_type_ctx.edit_origin(content="Aborted.", components=None)

    elif action_type_ctx.custom_id == "instant":
        success = await handle_assignment_group(selected_assignments, action)

        output_message = (
            config.message.tech_channel_message_success if success else config.message.tech_channel_message_fail
        ).format(
            **{
                "action": action,
                "type": "Instant",
                "assignments_groups": ", ".join(selected_assignments),
            }
        )
        return await action_type_ctx.edit_origin(
            content=output_message,
            components=None,
        )
    else:
        hours_ctx, arrow_dt_utc, arrow_dt = await handle_dt_picker(client, action_type_ctx)
        scheduler_name = f"{action} {', '.join(selected_assignments)}"
        scheduler.add_job(
            func=sched_assignment_group,
            trigger="date" if action_type_ctx.custom_id == "schedule" else None,
            run_date=arrow_dt_utc.datetime if action_type_ctx.custom_id == "schedule" else None,
            args=[
                selected_assignments,
                action,
            ],
            name=scheduler_name,
        )

        dt_format = f"{config.locale.datetime_format}"
        await hours_ctx.edit_origin(
            content=f"New job **{scheduler_name}** added. Will be fired at **{arrow_dt.format(dt_format)}**",
            components=None,
        )
