from typing import Set, Text, Dict, List, Tuple, Union

import arrow
import httpx
from discord import Client
from discord_slash import ComponentContext
from discord_slash.utils import manage_components

from rdmass.config import config
from rdmass.rdm import RDMGetApi, RDMSetApi


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
    ra = RDMGetApi()
    try:
        status = await ra.get_status()
    except httpx.RequestError as e:
        message = f"Status fetch failed!\nError: {type(e).__name__}: {e}"
    else:
        message = (
            (
                f"**Processing** {status['processing']['current']}/{status['processing']['max']} "
                f"({status['processing']['ignored']} ignored, {status['processing']['total']} total)\n"
                f"**Pokemon** {status['pokemon']['active_iv']}/{status['pokemon']['active_total']}\n"
                f"**Devices** {status['devices']['online']}/{status['devices']['total']}"
            )
            if status
            else "Status fetch failed!"
        )
    finally:
        return message


async def handle_dt_picker(client: Client, ctx: ComponentContext) -> Tuple[ComponentContext, arrow.Arrow, arrow.Arrow]:
    dt_now = arrow.now(config.locale.timezone).shift(hours=+1).replace(minute=0, second=0)

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
    hours_list = (
        arrow.Arrow.range("hour", dt_now, dt_now.shift(hours=+23))
        if days_ctx.selected_options[0] == days[0]["value"]
        else arrow.Arrow.range("hour", tmp_dt.replace(hour=0), tmp_dt.replace(hour=0).shift(hours=+23))
    )
    hours = [
        {
            "label": f"{dt.format(config.locale.date_format)} {dt.format(config.locale.time_format)}",
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
    dt_output_utc = dt_output.to("utc")

    return hours_ctx, dt_output_utc, dt_output


async def handle_assignment_group(assignments_groups: Union[Set, List[Text]], action: Text) -> bool:
    status = True
    try:
        ra = RDMSetApi()
        for assignment_group in assignments_groups:
            assert await ra.assignment_group(name=assignment_group, re_quest=action == "request")
    except (AssertionError, httpx.RequestError):
        status = False
    finally:
        return status
