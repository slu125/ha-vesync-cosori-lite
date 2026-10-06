"""Support for VeSync numeric entities."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import logging
from typing import override

from pyvesync.base_devices.fryer_base import VeSyncFryer
from pyvesync.base_devices.vesyncbasedevice import VeSyncBaseDevice
from pyvesync.device_container import DeviceContainer

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
    RestoreNumber,
)
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .common import is_air_fryer, is_humidifier
from .const import VS_DEVICES, VS_DISCOVERY
from .coordinator import VesyncConfigEntry, VeSyncDataCoordinator
from .entity import VeSyncBaseEntity
from .fryer import MAX_MINUTES, FryerProgram, get_program

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


def _mist_levels(device: VeSyncBaseDevice) -> list[int]:
    """Check if the device supports mist level adjustment."""
    if is_humidifier(device):
        return device.mist_levels
    raise HomeAssistantError("Device does not support mist level adjustment.")


def _set_mist_level(device: VeSyncBaseDevice, value: float) -> Awaitable[bool]:
    """Set mist level on humidifier."""
    if is_humidifier(device):
        return device.set_mist_level(int(value))
    raise HomeAssistantError("Device does not support mist level adjustment.")


@dataclass(frozen=True, kw_only=True)
class VeSyncNumberEntityDescription(NumberEntityDescription):
    """Class to describe a Vesync number entity."""

    exists_fn: Callable[[VeSyncBaseDevice], bool] = lambda _: True
    value_fn: Callable[[VeSyncBaseDevice], float]
    native_min_value_fn: Callable[[VeSyncBaseDevice], float]
    native_max_value_fn: Callable[[VeSyncBaseDevice], float]
    set_value_fn: Callable[[VeSyncBaseDevice, float], Awaitable[bool]]


NUMBER_DESCRIPTIONS: list[VeSyncNumberEntityDescription] = [
    VeSyncNumberEntityDescription(
        key="mist_level",
        translation_key="mist_level",
        native_min_value_fn=lambda device: min(_mist_levels(device)),
        native_max_value_fn=lambda device: max(_mist_levels(device)),
        native_step=1,
        mode=NumberMode.SLIDER,
        exists_fn=is_humidifier,
        set_value_fn=_set_mist_level,
        value_fn=lambda device: device.state.mist_virtual_level,
    )
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: VesyncConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up number entities."""

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


@callback
def _setup_entities(
    devices: DeviceContainer | list[VeSyncBaseDevice],
    async_add_entities: AddConfigEntryEntitiesCallback,
    coordinator: VeSyncDataCoordinator,
) -> None:
    """Add number entities."""

    entities: list[NumberEntity] = [
        VeSyncNumberEntity(dev, description, coordinator)
        for dev in devices
        for description in NUMBER_DESCRIPTIONS
        if description.exists_fn(dev)
    ]
    for dev in devices:
        if is_air_fryer(dev):
            entities.append(VeSyncFryerProgramTemperature(dev, coordinator))
            entities.append(VeSyncFryerProgramDuration(dev, coordinator))
    async_add_entities(entities)


class VeSyncNumberEntity(VeSyncBaseEntity, NumberEntity):
    """A class to set numeric options on Vesync device."""

    entity_description: VeSyncNumberEntityDescription

    def __init__(
        self,
        device: VeSyncBaseDevice,
        description: VeSyncNumberEntityDescription,
        coordinator: VeSyncDataCoordinator,
    ) -> None:
        """Initialize the VeSync number device."""
        super().__init__(device, coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{super().unique_id}-{description.key}"

    @property
    @override
    def native_value(self) -> float:
        """Return the value reported by the number."""
        return self.entity_description.value_fn(self.device)

    @property
    @override
    def native_min_value(self) -> float:
        """Return the value reported by the number."""
        return self.entity_description.native_min_value_fn(self.device)

    @property
    @override
    def native_max_value(self) -> float:
        """Return the value reported by the number."""
        return self.entity_description.native_max_value_fn(self.device)

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        if not await self.entity_description.set_value_fn(self.device, value):
            raise HomeAssistantError(self.device.last_response.message)
        self.async_write_ha_state()


class VeSyncFryerProgramNumber(VeSyncBaseEntity[VeSyncFryer], RestoreNumber):
    """Value of the cook program kept in Home Assistant."""

    _attr_mode = NumberMode.BOX
    _program_attr: str

    def __init__(self, device: VeSyncFryer, coordinator: VeSyncDataCoordinator) -> None:
        """Initialize the program number."""
        super().__init__(device, coordinator)
        self._attr_unique_id = f"{super().unique_id}-{self._attr_translation_key}"

    @override
    async def async_added_to_hass(self) -> None:
        """Restore the last value."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_number_data()) is not None and (
            last.native_value is not None
        ):
            value = min(
                max(last.native_value, self.native_min_value), self.native_max_value
            )
            setattr(self._program, self._program_attr, int(value))

    @property
    def _program(self) -> FryerProgram:
        return get_program(self.coordinator, self.device)

    @property
    @override
    def native_value(self) -> float:
        """Return the program value."""
        return getattr(self._program, self._program_attr)

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Change the program value."""
        setattr(self._program, self._program_attr, int(value))
        self.async_write_ha_state()


class VeSyncFryerProgramTemperature(VeSyncFryerProgramNumber):
    """Temperature of the cook program."""

    _attr_translation_key = "cook_program_temperature"
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _program_attr = "temperature"

    @property
    @override
    def native_min_value(self) -> float:
        """Return the lowest temperature."""
        return self.device.min_temp

    @property
    @override
    def native_max_value(self) -> float:
        """Return the highest temperature."""
        return self.device.max_temp

    @property
    @override
    def native_step(self) -> float:
        """Return the temperature step."""
        return self.device.temperature_step

    @property
    @override
    def native_unit_of_measurement(self) -> str:
        """Return the temperature unit of the fryer."""
        if str(self.device.temp_unit).lower() in ("f", "fahrenheit"):
            return UnitOfTemperature.FAHRENHEIT
        return UnitOfTemperature.CELSIUS


class VeSyncFryerProgramDuration(VeSyncFryerProgramNumber):
    """Duration of the cook program."""

    _attr_translation_key = "cook_program_duration"
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_native_min_value = 1
    _attr_native_max_value = MAX_MINUTES
    _attr_native_step = 1
    _program_attr = "minutes"
