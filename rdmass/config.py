import json
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from discord_slash.model import SlashCommandPermissionType
from discord_slash.utils.manage_commands import create_permission
from dotted_dict import DottedDict
from pydantic.utils import deep_update

# open config files
script_path = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(script_path, "..", "default.json"), "r") as f:
    default_config = json.load(f)
with open(os.path.join(script_path, "..", "config.json"), "r") as f:
    user_config = json.load(f)

# merge configs & DottedDict
config = deep_update(default_config, user_config)
config = DottedDict(config)

# prepare permissions dict
permissions = {
    config.instance.discord.guild_id: [
        create_permission(role_id, SlashCommandPermissionType.ROLE, True)
        for role_id in config.instance.discord.enabled_roles
    ]
}
permissions[config.instance.discord.guild_id].append(
    create_permission(config.instance.discord.guild_id, SlashCommandPermissionType.ROLE, False)
)

# scheduler configuration
scheduler = AsyncIOScheduler(
    {
        "apscheduler.jobstores.default": {"type": "sqlalchemy", "url": "sqlite:///jobs.sqlite"},
        "apscheduler.timezone": "UTC",
    }
)

__all__ = ["config", "permissions", "scheduler"]
