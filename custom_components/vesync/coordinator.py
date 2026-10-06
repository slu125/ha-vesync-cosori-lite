"""Class to manage VeSync data updates."""

from datetime import timedelta
import logging
import time
from typing import TYPE_CHECKING, override

from pyvesync import VeSync
from pyvesync.utils.errors import VeSyncError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    FRYER_FAST_POLL_AFTER_STAGE,
    UPDATE_INTERVAL,
    UPDATE_INTERVAL_ENERGY,
    UPDATE_INTERVAL_FRYER,
)

if TYPE_CHECKING:
    from .fryer import FryerProgram

_LOGGER = logging.getLogger(__name__)

type VesyncConfigEntry = ConfigEntry[VeSyncDataCoordinator]


class VeSyncDataCoordinator(DataUpdateCoordinator[None]):
    """Class representing data coordinator for VeSync devices."""

    config_entry: VesyncConfigEntry
    update_time: float | None = None
    fast_poll_until: float = 0.0

    def __init__(
        self, hass: HomeAssistant, config_entry: VesyncConfigEntry, manager: VeSync
    ) -> None:
        """Initialize."""
        self.manager = manager
        self.fryer_programs: dict[str, FryerProgram] = {}

        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name="VeSyncDataCoordinator",
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )

    def should_update_energy(self) -> bool:
        """Test if specified update interval has been exceeded."""
        if self.update_time is None:
            return True

        return time.time() - self.update_time >= UPDATE_INTERVAL_ENERGY

    def fast_poll_after_stage(self) -> None:
        """Poll fast for a while so a start on the appliance shows up quickly."""
        self.fast_poll_until = time.monotonic() + FRYER_FAST_POLL_AFTER_STAGE

    def _fryer_needs_fast_poll(self) -> bool:
        return time.monotonic() < self.fast_poll_until or any(
            fryer.state.is_running for fryer in self.manager.devices.air_fryers
        )

    @override
    async def _async_update_data(self) -> None:
        """Fetch data from API endpoint."""
        try:
            await self.manager.update_all_devices()

            if self.should_update_energy():
                self.update_time = time.time()
                for outlet in self.manager.devices.outlets:
                    await outlet.update_energy()
        except VeSyncError as err:
            raise UpdateFailed(f"The service is unavailable: {err}") from err
        finally:
            self.update_interval = timedelta(
                seconds=UPDATE_INTERVAL_FRYER
                if self._fryer_needs_fast_poll()
                else UPDATE_INTERVAL
            )
