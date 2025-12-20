"""Helper to create Home Assistant light groups for Hafele groups."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.group import DOMAIN as GROUP_DOMAIN
from homeassistant.components.group.light import LightGroup
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, EVENT_DEVICES_UPDATED
from .discovery import HafeleDiscovery

_LOGGER = logging.getLogger(__name__)


async def create_ha_groups_for_hafele_groups(
    hass: HomeAssistant,
    discovery: HafeleDiscovery,
) -> None:
    """Create Home Assistant helper groups for Hafele groups."""
    from homeassistant.helpers import group as group_helper
    
    groups = discovery.get_all_groups()
    devices = discovery.get_all_devices()
    
    # Build mapping of group addresses to device entity IDs
    # First, get all device entity IDs
    entity_registry = er.async_get(hass)
    all_device_entity_ids: list[str] = []
    for device_addr in devices.keys():
        unique_id = f"{device_addr}_mqtt"
        entity_id = entity_registry.async_get_entity_id("light", DOMAIN, unique_id)
        if entity_id:
            all_device_entity_ids.append(entity_id)
    
    # Map groups to their device entity IDs
    # Note: If groups have device information in their discovery payload, use that
    # For now, we'll try to get devices from group_info, but fall back to all devices
    group_to_devices: dict[int, list[str]] = {}
    for group_addr, group_info in groups.items():
        # Try to get device addresses from group info (various possible field names)
        device_addrs = (
            group_info.get("devices", [])
            or group_info.get("device_addrs", [])
            or group_info.get("device_addresses", [])
            or []
        )
        
        entity_ids = []
        if device_addrs:
            # Convert device addresses to entity IDs
            for device_addr in device_addrs:
                unique_id = f"{device_addr}_mqtt"
                entity_id = entity_registry.async_get_entity_id("light", DOMAIN, unique_id)
                if entity_id:
                    entity_ids.append(entity_id)
        
        # If no specific devices found, use all devices (especially for TOS_Internal_All)
        if not entity_ids and all_device_entity_ids:
            entity_ids = all_device_entity_ids.copy()
        
        if entity_ids:
            group_to_devices[group_addr] = entity_ids
    
    # Create HA groups for each Hafele group
    for group_addr, group_info in groups.items():
        group_name = group_info.get("group_name", f"group_{group_addr}")
        
        # Special case for TOS_Internal_All - use friendly name
        if group_name == "TOS_Internal_All":
            ha_group_name = "All hafele lights"
        else:
            # Add "group" suffix
            ha_group_name = f"{group_name} group"
        
        # Generate entity_id from name
        import re
        entity_id_base = ha_group_name.lower().replace(" ", "_").replace("-", "_")
        entity_id_base = re.sub(r"[^a-z0-9_]", "", entity_id_base)
        group_entity_id = f"light.{entity_id_base}"
        
        # Get device entity IDs for this group
        device_entity_ids = group_to_devices.get(group_addr, [])
        
        if not device_entity_ids:
            _LOGGER.debug(
                "Skipping HA group creation for %s - no device entities found",
                group_name,
            )
            continue
        
        # Check if group already exists
        entity_registry = er.async_get(hass)
        existing_entity_id = entity_registry.async_get_entity_id(
            "light", GROUP_DOMAIN, group_entity_id
        )
        
        if existing_entity_id:
            _LOGGER.debug(
                "HA group %s already exists (entity_id: %s), skipping",
                ha_group_name,
                existing_entity_id,
            )
            continue
        
        _LOGGER.info(
            "Creating HA helper group '%s' with %d lights",
            ha_group_name,
            len(device_entity_ids),
        )
        
        # Create the group using Home Assistant's group integration
        # We'll use the group.set service to create it
        try:
            await hass.services.async_call(
                GROUP_DOMAIN,
                "set",
                {
                    "object_id": entity_id_base,
                    "name": ha_group_name,
                    "entities": device_entity_ids,
                    "icon": "mdi:lightbulb-group",
                },
            )
            _LOGGER.info("Created HA helper group '%s'", ha_group_name)
        except Exception as err:
            _LOGGER.error(
                "Error creating HA helper group '%s': %s",
                ha_group_name,
                err,
            )

