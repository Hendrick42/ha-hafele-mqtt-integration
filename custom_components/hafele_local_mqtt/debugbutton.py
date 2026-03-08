"""Debug / ping button entity for Hafele Local MQTT."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    DOMAIN,
    TOPIC_GET_DEVICE_CTL,
    TOPIC_GET_DEVICE_LIGHTNESS,
    TOPIC_GET_DEVICE_POWER,
)
from .mqtt_client import HafeleMQTTClient

_LOGGER = logging.getLogger(__name__)


class HafelePingButton(ButtonEntity):
    """Representation of a Hafele ping button."""

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Disable ping entities by default; user can enable in entity registry if needed."""
        return False

    def __init__(
        self,
        mqtt_client: HafeleMQTTClient,
        device_addr: int,
        device_info: dict[str, Any],
        device_name: str,
        topic_prefix: str,
        button_type: str,  # "lightness" or "power"
        button_name: str,
        unique_id: str,
    ) -> None:
        """Initialize the button."""
        self.mqtt_client = mqtt_client
        self.device_addr = device_addr
        self.device_info = device_info
        self.device_name = device_name
        self.topic_prefix = topic_prefix
        self.button_type = button_type
        self._attr_unique_id = unique_id
        self._attr_name = button_name
        self._attr_has_entity_name = True

        # Device info - link to the light device
        # Use the same identifier format as the light entity
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(device_addr))},
            name=device_name,
            manufacturer="Hafele",
            model="Local MQTT Light",
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        if self.button_type == "lightness":
            # Check if device is multiwhite/RGB by checking device_info
            device_types = self.device_info.get("device_types", [])
            is_multiwhite = any(
                isinstance(dt, str) and dt.lower() in ("multiwhite", "rgb")
                for dt in device_types
            )
            
            if is_multiwhite:
                # Multiwhite/RGB devices use CTL topic
                topic = TOPIC_GET_DEVICE_CTL.format(
                    prefix=self.topic_prefix, device_name=self.device_name
                )
                _LOGGER.debug("Ping lightness button pressed for Multiwhite or RGB device %s", self.device_addr)
            else:
                # Monochrome devices use lightness topic
                topic = TOPIC_GET_DEVICE_LIGHTNESS.format(
                    prefix=self.topic_prefix, device_name=self.device_name
                )
                _LOGGER.debug("Ping lightness button pressed for Monochrome device %s", self.device_addr)
        elif self.button_type == "power":
            topic = TOPIC_GET_DEVICE_POWER.format(
                prefix=self.topic_prefix, device_name=self.device_name
            )
            _LOGGER.debug("Ping power button pressed for device %s", self.device_addr)
        else:
            _LOGGER.error("Unknown button type: %s", self.button_type)
            return

        # Publish empty payload to request status
        await self.mqtt_client.async_publish(topic, {}, qos=1)
        _LOGGER.info("Sent %s get request for device %s", self.button_type, self.device_addr)
