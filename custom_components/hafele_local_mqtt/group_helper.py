"""Helper to create Home Assistant light groups for Hafele groups."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.light.group import LightGroup
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import EntityPlatform

from .const import DOMAIN, EVENT_DEVICES_UPDATED
from .discovery import HafeleDiscovery

_LOGGER = logging.getLogger(__name__)


async def create_ha_groups_for_hafele_groups(
    hass: HomeAssistant,
    discovery: HafeleDiscovery,
) -> None:
    """Create Home Assistant light groups for Hafele groups."""
    groups = discovery.get_all_groups()
    
    # Build mapping of group addresses to device entity IDs
    # Use the "devices" field from the group discovery payload
    # The "devices" field contains a list of device_addr integers
    entity_registry = er.async_get(hass)
    group_to_devices: dict[int, list[str]] = {}
    
    for group_addr, group_info in groups.items():
        # Get device addresses from the "devices" field in the group discovery payload
        device_addrs = group_info.get("devices", [])
        
        if not device_addrs:
            _LOGGER.debug(
                "Group %s (addr: %s) has no devices field, skipping",
                group_info.get("group_name"),
                group_addr,
            )
            continue
        
        # Convert device addresses to entity IDs
        entity_ids = []
        for device_addr in device_addrs:
            # Find the entity ID for this device using its unique_id
            unique_id = f"{device_addr}_mqtt"
            entity_id = entity_registry.async_get_entity_id(LIGHT_DOMAIN, DOMAIN, unique_id)
            if entity_id:
                entity_ids.append(entity_id)
            else:
                _LOGGER.debug(
                    "Device %s (addr: %s) not found in entity registry for group %s",
                    device_addr,
                    group_addr,
                    group_info.get("group_name"),
                )
        
        if entity_ids:
            group_to_devices[group_addr] = entity_ids
            _LOGGER.debug(
                "Group %s (addr: %s) mapped to %d device entities",
                group_info.get("group_name"),
                group_addr,
                len(entity_ids),
            )
        else:
            _LOGGER.warning(
                "Group %s (addr: %s) has no valid device entities found",
                group_info.get("group_name"),
                group_addr,
            )
    
    # Create light groups for each Hafele group
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
        
        # Get device entity IDs for this group
        device_entity_ids = group_to_devices.get(group_addr, [])
        
        if not device_entity_ids:
            _LOGGER.debug(
                "Skipping light group creation for %s - no device entities found",
                group_name,
            )
            continue
        
        # Check if light group already exists
        unique_id = f"{group_addr}_light_group"
        existing_entity_id = entity_registry.async_get_entity_id(
            LIGHT_DOMAIN, DOMAIN, unique_id
        )
        
        if existing_entity_id:
            _LOGGER.debug(
                "Light group %s already exists (entity_id: %s), skipping",
                ha_group_name,
                existing_entity_id,
            )
            continue
        
        _LOGGER.info(
            "Creating light group '%s' with %d lights",
            ha_group_name,
            len(device_entity_ids),
        )
        
        # Create a proper light group entity using the light.group platform
        try:
            # Register the entity in the registry first
            entity_entry = entity_registry.async_get_or_create(
                LIGHT_DOMAIN,
                DOMAIN,
                unique_id,
                suggested_object_id=entity_id_base,
                name=ha_group_name,
            )
            
            # Create the LightGroup entity
            # LightGroup(name, entity_ids, mode=None, unique_id=None)
            light_group = LightGroup(
                ha_group_name,
                device_entity_ids,
                mode=None,  # Use default mode (all_on)
                unique_id=unique_id,
            )
            
            # Set up the entity
            light_group.hass = hass
            light_group.entity_id = entity_entry.entity_id
            
            # Get the light component and add the entity
            from homeassistant.helpers.entity_component import EntityComponent
            
            if LIGHT_DOMAIN not in hass.data:
                _LOGGER.warning("Light component not initialized, cannot create light group")
                continue
            
            light_component: EntityComponent = hass.data[LIGHT_DOMAIN]
            
            # Add the entity to the light component
            # This will properly register it as a light group
            await light_component.async_add_entities([light_group], update_before_add=False)
            
            _LOGGER.info("Created light group '%s' (entity_id: %s)", ha_group_name, entity_entry.entity_id)
            
        except Exception as err:
            _LOGGER.error(
                "Error creating light group '%s': %s",
                ha_group_name,
                err,
                exc_info=True,
            )
