import httpx
from typing import Dict, List, Optional, Text

from rdmass.config import config, logging

log = logging.getLogger(__name__)


async def client_get(url: Text, params: Dict) -> httpx.Response:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            url,
            auth=(config.instance.rdm.username, config.instance.rdm.password),
            headers={"user-agent": "rdmass/0.1"},
            params=params,
        )
        log.info(f"httpx GET {str(response.url).replace(config.instance.rdm.api_endpoint, '')}")

        return response


async def get_request(params: Dict) -> Optional[Dict]:
    response = await client_get(config.instance.rdm.api_endpoint + "/api/get_data", params)
    if response.status_code == httpx.codes.OK and response.json().get("status") == "ok":
        return response.json()


async def set_request(params: Dict) -> bool:
    response = await client_get(config.instance.rdm.api_endpoint + "/api/set_data", params)
    log.debug(f"set_request response code: {response.status_code}")
    return response.status_code == httpx.codes.OK


class RDMGetApi:
    @classmethod
    async def get_devices(cls) -> Optional[List[Dict]]:
        params = {"show_devices": True}

        output = await get_request(params)
        log.debug(f"RDMGetApi.get_devices: {output}")
        if output:
            return output["data"]["devices"]

    @classmethod
    async def get_instances(cls, skip_status: bool = True) -> Optional[List[Dict]]:
        params = {"show_instances": True, "skip_instance_status": skip_status}

        output = await get_request(params)
        log.debug(f"RDMGetApi.get_instances: {output}")
        if output:
            return output["data"]["instances"]

    @classmethod
    async def get_assignment_groups(cls) -> Optional[List[Dict]]:
        params = {"show_assignmentgroups": True}

        output = await get_request(params)
        log.debug(f"RDMGetApi.get_assignment_groups: {output}")
        if output:
            return output["data"]["assignmentgroups"]

    @classmethod
    async def get_status(cls) -> Optional[Dict]:
        params = {"show_status": True}

        output = await get_request(params)
        log.debug(f"RDMGetApi.get_status: {output}")
        if output:
            return output["data"]["status"]


class RDMSetApi:
    @classmethod
    async def assign_device(cls, device_name: Text, instance_name: Text) -> bool:
        params = {
            "assign_device": True,
            "device_name": device_name,
            "instance": instance_name,
        }

        output = await set_request(params)
        log.debug(f"RDMSetApi.assign_device: {output}")
        return output

    @classmethod
    async def assign_device_group(cls, device_group_name: Text, instance_name: Text) -> bool:
        params = {
            "assign_device_group": True,
            "device_group_name": device_group_name,
            "instance": instance_name,
        }

        output = await set_request(params)
        log.debug(f"RDMSetApi.assign_device_group: {output}")
        return output

    @classmethod
    async def assignment_group(cls, name: Text, re_quest: bool = False) -> bool:
        params = {
            "assignmentgroup_name": name,
            "assignmentgroup_re_quest": re_quest,
            "assignmentgroup_start": not re_quest,
        }

        output = await set_request(params)
        log.debug(f"RDMSetApi.assignment_group: {output}")
        return output

    @classmethod
    async def reload_instances(cls) -> bool:
        params = {"reload_instances": True}

        output = await set_request(params)
        log.debug(f"RDMSetApi.reload_instances: {output}")
        return output

    @classmethod
    async def clear_all_quests(cls) -> bool:
        params = {"clear_all_quests": True}

        output = await set_request(params)
        log.debug(f"RDMSetApi.clear_all_quests: {output}")
        return output
