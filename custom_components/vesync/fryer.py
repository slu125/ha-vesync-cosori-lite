"""Air fryer cook programs for VeSync.

A cook program (mode, temperature, duration) is kept per fryer in the
coordinator. Number and select entities edit it, the "send program" button
and the ``stage_cook_program`` action send it. Fryers such as the CAF-LI401S
only stage the program; it is started on the appliance.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from pyvesync.base_devices.fryer_base import VeSyncFryer
from pyvesync.base_devices.vesyncbasedevice import VeSyncBaseDevice

from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .common import is_air_fryer
from .coordinator import VeSyncDataCoordinator

DEFAULT_TEMPERATURE = 180
DEFAULT_MINUTES = 15
MAX_MINUTES = 120


@dataclass
class FryerProgram:
    """Cook program staged by Home Assistant."""

    mode: str
    temperature: int
    minutes: int


def mode_options(device: VeSyncBaseDevice) -> list[str]:
    """Return the cook modes of a fryer as option keys."""
    if not is_air_fryer(device):
        return []
    return [str(mode).lower() for mode in device.cook_modes.values()]


def default_mode(device: VeSyncFryer) -> str:
    """Return the option key of the fryer's default program."""
    return str(device.default_preset.cook_mode).lower()


def get_program(
    coordinator: VeSyncDataCoordinator, device: VeSyncFryer
) -> FryerProgram:
    """Return the cook program of a fryer, creating the default one."""
    if (program := coordinator.fryer_programs.get(device.cid)) is None:
        options = mode_options(device)
        mode = default_mode(device)
        program = coordinator.fryer_programs[device.cid] = FryerProgram(
            mode=mode if mode in options else options[0],
            temperature=min(max(DEFAULT_TEMPERATURE, device.min_temp), device.max_temp),
            minutes=DEFAULT_MINUTES,
        )
    return program


async def async_stage_program(
    coordinator: VeSyncDataCoordinator, device: VeSyncFryer, program: FryerProgram
) -> None:
    """Send a cook program to the fryer."""
    if program.mode not in mode_options(device):
        raise HomeAssistantError(f"Unknown cook mode {program.mode}")
    if (temperature := device.prepare_temperature(program.temperature)) is None:
        raise HomeAssistantError(
            f"Temperature must be between {device.min_temp} and {device.max_temp}"
        )
    seconds = program.minutes * 60
    if program.mode == default_mode(device):
        success = await device.set_mode(seconds, program.temperature)
    else:
        mode = next(
            str(value)
            for value in device.cook_modes.values()
            if str(value).lower() == program.mode
        )
        recipe = replace(
            device.default_preset,
            cook_mode=mode,
            cook_time=device.convert_time_for_api(seconds),
            target_temp=temperature,
        )
        success = await device.set_mode_from_recipe(recipe)
    if not success:
        raise HomeAssistantError(
            f"Could not send the cook program to {device.device_name}"
        )
    coordinator.fast_poll_after_stage()
    await coordinator.async_request_refresh()


def current_mode(device: VeSyncBaseDevice) -> str | None:
    """Return the cook mode of the running program as option key."""
    if not is_air_fryer(device) or not device.state.is_running:
        return None
    mode = str(device.state.cook_mode or "").lower()
    return mode if mode in mode_options(device) else None


def remaining_seconds(device: VeSyncBaseDevice) -> int | None:
    """Return the remaining preheat or cook time in seconds."""
    if not is_air_fryer(device):
        return None
    state = device.state
    if state.is_preheating:
        return state.preheat_time_remaining
    if state.is_cooking:
        return state.cook_time_remaining
    return None


def end_time(device: VeSyncBaseDevice) -> datetime | None:
    """Return when the running cook program ends (full minutes)."""
    if (
        not is_air_fryer(device)
        or not device.state.is_running
        or (remaining := remaining_seconds(device)) is None
    ):
        return None
    if device.state.is_preheating:
        remaining += device.state.cook_set_time or 0
    end = dt_util.utcnow() + timedelta(seconds=remaining)
    return end.replace(second=0, microsecond=0)
