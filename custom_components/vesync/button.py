"""Buttons for VeSync air fryers."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import logging
from typing import override

from pyvesync.base_devices.fryer_base import VeSyncFryer
from pyvesync.base_devices.vesyncbasedevice import VeSyncBaseDevice
from pyvesync.const import AirFryerFeatures
from pyvesync.device_container import DeviceContainer
import voluptuous as vol

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .common import is_air_fryer
from .const import VS_DEVICES, VS_DISCOVERY
from .coordinator import VesyncConfigEntry, VeSyncDataCoordinator
from .entity import VeSyncBaseEntity
from .fryer import MAX_MINUTES, FryerProgram, async_stage_program, get_program

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

SERVICE_STAGE_COOK_PROGRAM = "stage_cook_program"
ATTR_MODE = "mode"
ATTR_TEMPERATURE = "temperature"
ATTR_DURATION = "duration"


def _is_resumable(device: VeSyncBaseDevice) -> bool:
    # RESUMABLE is claimed by fryer classes that do not implement stop/resume
    return (
        is_air_fryer(device)
        and AirFryerFeatures.RESUMABLE in device.features
        and type(device).stop is not VeSyncFryer.stop
        and type(device).resume is not VeSyncFryer.resume
    )


@dataclass(frozen=True, kw_only=True)
class VeSyncButtonEntityDescription(ButtonEntityDescription):
    """Describe a VeSync air fryer button."""

    press_fn: Callable[[VeSyncFryer], Awaitable[bool]]
    exists_fn: Callable[[VeSyncBaseDevice], bool] = is_air_fryer


BUTTON_DESCRIPTIONS: tuple[VeSyncButtonEntityDescription, ...] = (
    VeSyncButtonEntityDescription(
        key="end_cooking",
        translation_key="end_cooking",
        press_fn=lambda device: device.end(),
    ),
    VeSyncButtonEntityDescription(
        key="pause_cooking",
        translation_key="pause_cooking",
        press_fn=lambda device: device.stop(),
        exists_fn=_is_resumable,
    ),
    VeSyncButtonEntityDescription(
        key="resume_cooking",
        translation_key="resume_cooking",
        press_fn=lambda device: device.resume(),
        exists_fn=_is_resumable,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: VesyncConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up button entities."""

    coordinator = config_entry.runtime_data

    @callback
    def discover(devices: list[VeSyncBaseDevice]) -> None:
        """Add new devices to platform."""
        _setup_entities(devices, async_add_entities, coordinator)

    config_entry.async_on_unload(
        async_dispatcher_connect(hass, VS_DISCOVERY.format(VS_DEVICES), discover)
    )

    _setup_entities(
        config_entry.runtime_data.manager.devices, async_add_entities, coordinator
    )

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_STAGE_COOK_PROGRAM,
        {
            vol.Optional(ATTR_MODE): cv.string,
            vol.Optional(ATTR_TEMPERATURE): vol.Coerce(int),
            vol.Optional(ATTR_DURATION): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=MAX_MINUTES)
            ),
        },
        "async_stage_program",
    )


@callback
def _setup_entities(
    devices: DeviceContainer | list[VeSyncBaseDevice],
    async_add_entities: AddConfigEntryEntitiesCallback,
    coordinator: VeSyncDataCoordinator,
) -> None:
    """Add button entities."""
    entities: list[ButtonEntity] = [
        VeSyncButtonEntity(dev, description, coordinator)
        for dev in devices
        for description in BUTTON_DESCRIPTIONS
        if is_air_fryer(dev) and description.exists_fn(dev)
    ]
    entities.extend(
        VeSyncStageProgramButton(dev, coordinator)
        for dev in devices
        if is_air_fryer(dev)
    )
    async_add_entities(entities)


class VeSyncButtonEntity(VeSyncBaseEntity[VeSyncFryer], ButtonEntity):
    """Button that sends a command to an air fryer."""

    entity_description: VeSyncButtonEntityDescription

    def __init__(
        self,
        device: VeSyncFryer,
        description: VeSyncButtonEntityDescription,
        coordinator: VeSyncDataCoordinator,
    ) -> None:
        """Initialize the button."""
        super().__init__(device, coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{super().unique_id}-{description.key}"

    @override
    async def async_press(self) -> None:
        """Send the command."""
        if not await self.entity_description.press_fn(self.device):
            raise HomeAssistantError(
                f"{self.device.device_name}: {self.entity_description.key} failed"
            )
        await self.coordinator.async_request_refresh()


class VeSyncStageProgramButton(VeSyncBaseEntity[VeSyncFryer], ButtonEntity):
    """Send the cook program set in Home Assistant to the fryer."""

    _attr_translation_key = "stage_cook_program"

    def __init__(self, device: VeSyncFryer, coordinator: VeSyncDataCoordinator) -> None:
        """Initialize the button."""
        super().__init__(device, coordinator)
        self._attr_unique_id = f"{super().unique_id}-stage_cook_program"

    @override
    async def async_press(self) -> None:
        """Send the current cook program."""
        await async_stage_program(
            self.coordinator, self.device, get_program(self.coordinator, self.device)
        )

    async def async_stage_program(
        self,
        mode: str | None = None,
        temperature: int | None = None,
        duration: int | None = None,
    ) -> None:
        """Send a cook program given by the action, defaults from the entities."""
        current = get_program(self.coordinator, self.device)
        program = FryerProgram(
            mode=mode.lower() if mode is not None else current.mode,
            temperature=temperature if temperature is not None else current.temperature,
            minutes=duration if duration is not None else current.minutes,
        )
        await async_stage_program(self.coordinator, self.device, program)
