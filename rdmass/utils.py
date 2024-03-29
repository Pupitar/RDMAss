import aiofiles
import aiofiles.os
import arrow
import httpx
import simplejson as json
from datetime import timedelta
from dateutil import tz
from discord import Client
from discord_slash import ComponentContext
from discord_slash.utils import manage_components
from sentry_sdk import capture_exception
from timeit import default_timer as timer
from typing import Set, Text, Dict, List, Tuple, Union, cast, Any, Callable, TypeVar, Optional
from dataclasses import dataclass

from rdmass.config import config, logging, scheduler, past_events_path
from rdmass.rdm import RDMGetApi, RDMSetApi

log = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class Event:
    name: str
    type: str
    has_quests: bool
    accepted_hours: bool = False
    accepted_diff: bool = False
    date: Optional[str] = None
    date_arrow: Optional[arrow.arrow.Arrow] = None


def create_action_list(
    rows: List[Dict], placeholder: Text, custom_id: Text, selected: Set = None, show_previous: bool = True
) -> Dict:
    button_next = {"label": "Next page...", "value": "button_next", "description": "Show next page", "default": False}
    button_previous = {
        "label": "Previous page...",
        "value": "button_previous",
        "description": "Show previous page",
        "default": False,
    }
    button_close = {
        "label": "Save & Close",
        "value": "button_close",
        "description": "Save & Close selection",
        "default": False,
    }

    rows = [
        {
            "label": row["label"],
            "value": row["value"],
            "description": row.get("description"),
            "default": row["value"] in selected
            and row["value"] not in ("button_next", "button_previous", "button_close"),
        }
        for row in rows
    ]

    if show_previous:
        rows.insert(0, button_previous)

    if len(rows) < 23:
        rows.append(button_close)
    else:
        rows.append(button_next)

    action_list = [
        manage_components.create_select(
            custom_id=custom_id,
            placeholder=placeholder,
            min_values=1,
            max_values=len(rows),
            options=rows,
        )
    ]
    action_row = manage_components.create_actionrow(*action_list)

    return action_row


async def handle_bot_list(
    client: Client,
    ctx: ComponentContext,
    rows: List[Dict],
    initial_message: Text,
    placeholder: Text,
    custom_id: Text,
    edit_component: ComponentContext = None,
    remember_selected: bool = True,
) -> Tuple[ComponentContext, Set]:
    saved_choices = set()
    current_choices = rows[:23]

    action_row = create_action_list(
        current_choices, placeholder, custom_id, selected=saved_choices, show_previous=False
    )

    if edit_component:
        await edit_component.edit_origin(content=initial_message, components=[action_row])
    else:
        await ctx.send(initial_message, components=[action_row], hidden=config.bot.hide_bot_message)

    index = 0
    keep_open = True

    # loop for components response then quit or re-create
    while keep_open:
        assignment_groups = await manage_components.wait_for_component(client, components=action_row)
        if remember_selected:
            saved_choices = saved_choices.union(assignment_groups.selected_options)

            for discard in ["button_next", "button_previous", "button_close"]:
                saved_choices.discard(discard)

        if index < 0:
            index = 0

        if "button_next" in assignment_groups.selected_options:
            index += 1
            current_choices = rows[index * 23 : (index * 23) + 23]
            action_row = create_action_list(
                current_choices, placeholder, custom_id, selected=saved_choices, show_previous=index != 0
            )
        elif "button_previous" in assignment_groups.selected_options:
            index -= 1
            current_choices = rows[index * 23 : (index * 23) + 23]
            action_row = create_action_list(
                current_choices, placeholder, custom_id, selected=saved_choices, show_previous=index != 0
            )
        elif "button_close" in assignment_groups.selected_options:
            keep_open = False
        else:
            keep_open = False

        if not current_choices:
            keep_open = False

        if keep_open:
            await assignment_groups.edit_origin(
                content=f"Selected: {', '.join(saved_choices)}", components=[action_row]
            )
        else:
            return assignment_groups, saved_choices


# noinspection PyUnboundLocalVariable
async def get_status_message() -> Text:
    try:
        status = await RDMGetApi.get_status()
    except httpx.RequestError as e:
        capture_exception(e)
        message = f"Status fetch failed!\nError: {type(e).__name__}: {e}"
    else:
        message = (
            (
                f"**Processing** {status['processing']['current']}/{status['processing']['max']} "
                f"({status['processing']['ignored']} ignored, {status['processing']['total']} total)\n"
                f"**Pokemon** {status['pokemon']['active_iv']}/{status['pokemon']['active_total']} "
                f"({status['pokemon']['active_iv'] / (status['pokemon']['active_total'] or 1) * 100:.2f}%)\n"
                f"**Devices** {status['devices']['online']}/{status['devices']['total']}"
            )
            if status
            else "Status fetch failed!"
        )
    finally:
        return message


async def handle_dt_picker(client: Client, ctx: ComponentContext) -> Tuple[ComponentContext, arrow.Arrow, arrow.Arrow]:
    dt_now = arrow.now(config.locale.timezone).replace(minute=0, second=0)

    # DAYS
    days = [
        {"label": f"{dt.format(config.locale.date_format)}", "value": f"{dt.year},{dt.month},{dt.day}"}
        for dt in arrow.Arrow.range("day", dt_now, dt_now.shift(days=+23))
    ]

    action_list = [
        manage_components.create_select(
            custom_id="dt_day_picker",
            placeholder="...",
            min_values=1,
            max_values=1,
            options=days,
        )
    ]
    action_row = manage_components.create_actionrow(*action_list)
    await ctx.edit_origin(content="Pick a day", components=[action_row])

    days_ctx = await manage_components.wait_for_component(client, components=action_row)
    year, month, day = map(int, days_ctx.selected_options[0].split(","))

    tmp_dt = dt_now.replace(year=year, month=month, day=day, hour=0)

    # HOURS
    hours_list = (
        arrow.Arrow.range("hour", dt_now, dt_now.shift(hours=+23))
        if days_ctx.selected_options[0] == days[0]["value"]
        else arrow.Arrow.range("hour", tmp_dt.replace(hour=0), tmp_dt.replace(hour=0).shift(hours=+23))
    )
    hours = [
        {
            "label": f"{dt.format(config.locale.datetime_format)}",
            "value": f"{dt.year},{dt.month},{dt.day},{dt.hour}",
        }
        for dt in hours_list
    ]

    action_list = [
        manage_components.create_select(
            custom_id="dt_hour_picker",
            placeholder="...",
            min_values=1,
            max_values=1,
            options=hours,
        )
    ]
    action_row = manage_components.create_actionrow(*action_list)
    await days_ctx.edit_origin(content="Pick an hour", components=[action_row])

    hours_ctx = await manage_components.wait_for_component(client, components=action_row)
    year, month, day, hour = map(int, hours_ctx.selected_options[0].split(","))
    dt_output = arrow.Arrow(year, month, day, hour, tzinfo=config.locale.timezone)

    # MINUTES
    minutes = [
        {
            "label": f"{dt_output.format(config.locale.date_format)} "
            f"{dt_output.replace(minute=minute).format(config.locale.time_format)}",
            "value": f"{minute:02d}",
        }
        for minute in list(range(0, 60, 5))
    ]

    action_list = [
        manage_components.create_select(
            custom_id="dt_minutes_picker",
            placeholder="...",
            min_values=1,
            max_values=1,
            options=minutes,
        )
    ]
    action_row = manage_components.create_actionrow(*action_list)
    await hours_ctx.edit_origin(content="Pick minute", components=[action_row])

    minutes_ctx = await manage_components.wait_for_component(client, components=action_row)

    dt_output = dt_output.replace(minute=int(minutes_ctx.selected_options[0]))
    dt_output_utc = dt_output.to("utc")

    return minutes_ctx, dt_output_utc, dt_output


async def handle_assignment_group(assignments_groups: Union[Set, List[Text]], action: Text) -> bool:
    status = True
    try:
        ra = RDMSetApi()
        for assignment_group in assignments_groups:
            assert await ra.assignment_group(name=assignment_group, re_quest=action == "request")
    except (AssertionError, httpx.RequestError) as e:
        capture_exception(e)
        status = False
    finally:
        return status


async def handle_clean() -> bool:
    status = True
    try:
        assert await RDMSetApi.clear_all_quests()
    except (AssertionError, httpx.RequestError) as e:
        capture_exception(e)
        status = False
    finally:
        return status


def timeit(func: F) -> F:
    def wrapper(*args, **kwargs):
        start = timer()
        result = func(*args, **kwargs)
        end = timer()
        log.debug(f"{func.__name__} took {timedelta(seconds=end-start)}")
        return result

    return cast(F, wrapper)


# TODO: Auto migrate old Schedules. Remove me after some time
def scheduler_migration() -> None:
    for job in scheduler.get_jobs():
        if len(job.args) > 2:
            scheduler.modify_job(job_id=job.id, args=job.args[:2])


async def handle_auto_events(bot_client: Client, scheduler_target: Any) -> None:
    # sanity checks
    if not config.auto_event.enabled and config.auto_event.quest_instances:
        return

    # check if past_events file exists
    past_events_path_exists = await aiofiles.os.path.exists(past_events_path)
    if not past_events_path_exists:
        log.debug("handle_events - creating past_events file")
        past_event_dates = {"main": set(), "filtered": set()}
        async with aiofiles.open(past_events_path, mode="w") as f:
            await f.write(json.dumps(past_event_dates, iterable_as_array=True))

    else:
        log.debug("handle_events - loaded past_events file")
        # load previously added job dates
        async with aiofiles.open(past_events_path, mode="r") as f:
            contents = await f.read()
            past_event_dates = json.loads(contents)

            # remove someday :^)
            if isinstance(past_event_dates, list):
                past_event_dates = {"main": set(past_event_dates), "filtered": set()}
            else:
                past_event_dates = {
                    "main": set(past_event_dates["main"]),
                    "filtered": set(past_event_dates["filtered"]),
                }

    # fetch events from remote
    async with httpx.AsyncClient(timeout=config.auto_event.http_timeout) as client:
        response = await client.get(config.resource.pogoinfo_events, headers={"user-agent": config.bot.user_agent})
        log.info(f"httpx GET pogoinfo events")

    raw_events = response.json()
    log.debug("handle_events - fetched pogoinfo events")

    events = []
    filtered_events = []
    beginning_dates = set()
    beginning_dates_filtered = set()
    now = arrow.now(tz=config.locale.timezone)

    # iterate all events in source and created 2 events (starting and ending) for each event
    for event_row in raw_events:
        # include only selected event types
        if event_row["type"] not in config.auto_event.types:
            continue

        # process both start and the end of the event
        for event_type in ("start", "end"):
            event = Event(
                name=event_row["name"],
                type=event_row["type"],
                has_quests=event_row["has_quests"],
            )

            if not event_row[event_type]:
                continue

            event.beginning = event_type == "start"
            event.date = event_row["start"] if event.beginning else event_row["end"]
            event.date_arrow = arrow.get(event.date, tzinfo=config.locale.timezone)

            if config.auto_event.time_range[0] <= event.date_arrow.hour <= config.auto_event.time_range[1]:
                event.accepted_hours = True

            if (event.date_arrow - now).total_seconds() > config.auto_event.skip_diff:
                event.accepted_diff = True

            if event.has_quests and event.accepted_hours and event.accepted_diff:
                if event.beginning:
                    beginning_dates.add(event.date)
                events.append(event)
            else:
                if event.beginning:
                    beginning_dates_filtered.add(event.date)
                filtered_events.append(event)

    log.debug(f"handle_events - got {len(events)} events before cleanup")

    # use end events only when there's no beginning event with same date
    events = [
        event
        for event in events
        if event.date not in past_event_dates["main"]
        and (event.beginning or not event.beginning and event.date not in beginning_dates)
    ]

    filtered_events = [
        event
        for event in filtered_events
        if event.date not in past_event_dates["filtered"].union(past_event_dates["main"])
        and (event.beginning or not event.beginning and event.date not in beginning_dates_filtered)
    ]

    if not events and not filtered_events:
        log.debug(f"handle_events - no events to process")
        return

    log.debug(f"handle_events - got {len(events)} events and {len(filtered_events)} after cleanup")

    # add events
    tech_output_message = config.message.tech_auto_event_header
    user_output_message = config.message.user_auto_event_header
    tech_output_filtered_message = config.message.tech_auto_event_filtered_header

    for event in events:
        iv_run_date = event.date_arrow + timedelta(minutes=config.auto_event.execution_time)

        message_data = {
            "date": event.date_arrow.format(config.locale.datetime_format),
            "name": event.name,
            "has_quests": ":regional_indicator_q:" if event.has_quests else "",
            "accepted_hours": ":regional_indicator_h:" if event.accepted_hours else "",
            "state": (config.message.user_auto_event_start if event.beginning else config.message.user_auto_event_end),
        }
        user_output_message += config.message.user_auto_event_request.format(**message_data)
        message_data["state"] = (
            config.message.tech_auto_event_start if event.beginning else config.message.tech_auto_event_end
        )
        tech_output_message += config.message.tech_auto_event_request.format(**message_data)

        scheduler.add_job(
            id=f"{event.date}-1",
            func=scheduler_target,
            trigger="date",
            run_date=event.date_arrow.to("UTC").datetime,
            name=config.message.tech_auto_event_request_short.format(**message_data),
            args=[
                config.auto_event.quest_instances,
                "request",
            ],
            replace_existing=True,
        )

        message_data["date"] = iv_run_date.format(config.locale.datetime_format)

        if config.auto_event.iv_instances:
            user_output_message += config.message.user_auto_event_iv.format(**message_data)
            tech_output_message += config.message.tech_auto_event_iv.format(**message_data)

            scheduler.add_job(
                id=f"{event.date}-2",
                func=scheduler_target,
                trigger="date",
                run_date=iv_run_date.to("UTC").datetime,
                name=config.message.tech_auto_event_iv_short.format(**message_data),
                args=[
                    config.auto_event.iv_instances,
                    "start",
                ],
                replace_existing=True,
            )

        log.debug(f"handle_events - added event {event.name} at {event.date} to scheduler")
        past_event_dates["main"].add(event.date)

    for event in filtered_events:
        message_data = {
            "date": event.date_arrow.format(config.locale.datetime_format),
            "name": event.name,
            "has_quests": ":regional_indicator_q:" if event.has_quests else "",
            "accepted_hours": ":regional_indicator_h:" if event.accepted_hours else "",
            "state": (config.message.tech_auto_event_start if event.beginning else config.message.tech_auto_event_end),
        }
        tech_output_filtered_message += config.message.tech_auto_event_filtered.format(**message_data)
        past_event_dates["filtered"].add(event.date)

    # save event dates
    async with aiofiles.open(past_events_path, mode="w") as f:
        log.debug(f"handle_events - saving past_events file")
        await f.write(json.dumps(past_event_dates, iterable_as_array=True))

    # handle tech messages
    if config.instance.discord.tech_channel and tech_output_message:
        tech_channel = await bot_client.fetch_channel(config.instance.discord.tech_channel)

        if events:
            await tech_channel.send(tech_output_message)
        if filtered_events:
            await tech_channel.send(tech_output_filtered_message)

    # handle user messages
    if config.instance.discord.user_channel and user_output_message and events:
        user_channel = await bot_client.fetch_channel(config.instance.discord.user_channel)

        await user_channel.send(user_output_message)
