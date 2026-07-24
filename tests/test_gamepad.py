import os
from pathlib import Path

import pytest

import dw_cli.gamepad as gamepad_module
from dw_cli.gamepad import (
    BTN_DPAD_DOWN,
    BTN_DPAD_LEFT,
    BTN_DPAD_RIGHT,
    BTN_DPAD_UP,
    BTN_EAST,
    BTN_NORTH,
    BTN_SOUTH,
    BTN_WEST,
    JS_EVENT_AXIS,
    JS_EVENT_BUTTON,
    JS_EVENT_INIT,
    JSIOCGBTNMAP,
    JSIOCGBUTTONS,
    InputAction,
    LinuxJoystick,
)


def joystick() -> LinuxJoystick:
    descriptor = os.open(os.devnull, os.O_RDONLY)
    return LinuxJoystick(Path(os.devnull), descriptor)


def test_common_r36s_buttons() -> None:
    device = joystick()
    try:
        assert device.decode_event(1, JS_EVENT_BUTTON, 0) == InputAction.BACK
        assert device.decode_event(1, JS_EVENT_BUTTON, 1) == InputAction.SELECT
        assert device.decode_event(1, JS_EVENT_BUTTON, 2) == InputAction.SUBMIT_SEARCH
        assert device.decode_event(1, JS_EVENT_BUTTON, 3) == InputAction.BACKSPACE
        assert device.decode_event(1, JS_EVENT_BUTTON, 4) == InputAction.PAGE_UP
        assert device.decode_event(1, JS_EVENT_BUTTON, 7) == InputAction.START
        assert device.decode_event(1, JS_EVENT_BUTTON, 9) == InputAction.START
        assert device.decode_event(0, JS_EVENT_BUTTON, 0) is None
    finally:
        device.close()


def test_kernel_button_map_overrides_raw_indices_for_dpad_and_face_buttons() -> None:
    device = joystick()
    device._button_codes = (
        BTN_DPAD_UP,
        BTN_DPAD_DOWN,
        BTN_DPAD_LEFT,
        BTN_DPAD_RIGHT,
        BTN_SOUTH,
        BTN_EAST,
        BTN_NORTH,
        BTN_WEST,
    )
    try:
        assert device.decode_event(1, JS_EVENT_BUTTON, 0) == InputAction.UP
        assert device.decode_event(1, JS_EVENT_BUTTON, 1) == InputAction.DOWN
        assert device.decode_event(1, JS_EVENT_BUTTON, 2) == InputAction.LEFT
        assert device.decode_event(1, JS_EVENT_BUTTON, 3) == InputAction.RIGHT
        assert device.decode_event(1, JS_EVENT_BUTTON, 4) == InputAction.BACK
        assert device.decode_event(1, JS_EVENT_BUTTON, 5) == InputAction.SELECT
        assert device.decode_event(1, JS_EVENT_BUTTON, 6) == InputAction.SUBMIT_SEARCH
        assert device.decode_event(1, JS_EVENT_BUTTON, 7) == InputAction.BACKSPACE
    finally:
        device.close()


def test_kernel_button_map_is_read_from_joydev_ioctl(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = (BTN_DPAD_UP, BTN_DPAD_DOWN, BTN_DPAD_LEFT, BTN_DPAD_RIGHT)

    def fake_ioctl(
        _descriptor: int,
        request: int,
        buffer: bytearray,
        _mutate: bool,
    ) -> int:
        if request == JSIOCGBUTTONS:
            buffer[0] = len(expected)
        elif request == JSIOCGBTNMAP:
            for index, code in enumerate(expected):
                buffer[index * 2 : index * 2 + 2] = code.to_bytes(2, byteorder="little")
        return 0

    monkeypatch.setattr(gamepad_module.fcntl, "ioctl", fake_ioctl)

    assert LinuxJoystick._read_button_codes(42) == expected


def test_dpad_axes_emit_once_until_released() -> None:
    device = joystick()
    try:
        assert device.decode_event(-32_767, JS_EVENT_AXIS, 6) == InputAction.LEFT
        assert device.decode_event(-32_767, JS_EVENT_AXIS, 6) is None
        assert device.decode_event(0, JS_EVENT_AXIS, 6) is None
        assert device.decode_event(32_767, JS_EVENT_AXIS, 7) == InputAction.DOWN
    finally:
        device.close()


def test_r36s_dpad_buttons_map_to_all_four_directions() -> None:
    device = joystick()
    try:
        assert device.decode_event(0, JS_EVENT_BUTTON | JS_EVENT_INIT, 17) is None
        assert device.decode_event(1, JS_EVENT_BUTTON, 14) == InputAction.UP
        assert device.decode_event(1, JS_EVENT_BUTTON, 15) == InputAction.DOWN
        assert device.decode_event(1, JS_EVENT_BUTTON, 16) == InputAction.LEFT
        assert device.decode_event(1, JS_EVENT_BUTTON, 17) == InputAction.RIGHT
        assert device.decode_event(0, JS_EVENT_BUTTON, 14) is None
    finally:
        device.close()


def test_standard_dpad_button_layout_is_detected_from_initialization() -> None:
    device = joystick()
    try:
        assert device.decode_event(0, JS_EVENT_BUTTON | JS_EVENT_INIT, 14) is None
        assert device.decode_event(1, JS_EVENT_BUTTON, 11) == InputAction.UP
        assert device.decode_event(1, JS_EVENT_BUTTON, 12) == InputAction.DOWN
        assert device.decode_event(1, JS_EVENT_BUTTON, 13) == InputAction.LEFT
        assert device.decode_event(1, JS_EVENT_BUTTON, 14) == InputAction.RIGHT
    finally:
        device.close()


def test_r36s_sticks_support_standard_rx_and_ry_axes() -> None:
    device = joystick()
    try:
        assert device.decode_event(32_767, JS_EVENT_AXIS, 0) == InputAction.RIGHT
        assert device.decode_event(-32_767, JS_EVENT_AXIS, 3) == InputAction.UP
        assert device.decode_event(32_767, JS_EVENT_AXIS, 4) == InputAction.DOWN
        assert device.decode_event(32_767, JS_EVENT_AXIS, 5) is None
    finally:
        device.close()


def test_initialization_events_are_ignored() -> None:
    device = joystick()
    try:
        assert device.decode_event(1, JS_EVENT_BUTTON | JS_EVENT_INIT, 0) is None
    finally:
        device.close()


@pytest.mark.parametrize(
    ("event_type", "number"),
    ((JS_EVENT_BUTTON, 15), (JS_EVENT_AXIS, 7)),
)
def test_holding_down_repeats_until_release(
    monkeypatch: pytest.MonkeyPatch,
    event_type: int,
    number: int,
) -> None:
    clock = [10.0]
    monkeypatch.setattr(gamepad_module, "monotonic", lambda: clock[0])
    device = joystick()
    pressed_value = 1 if event_type == JS_EVENT_BUTTON else 32_767
    released_value = 0
    try:
        assert device.decode_event(pressed_value, event_type, number) == InputAction.DOWN
        clock[0] += gamepad_module.REPEAT_DELAY_SECONDS - 0.01
        assert device.poll() is None
        clock[0] += 0.01
        assert device.poll() == InputAction.DOWN
        clock[0] += gamepad_module.REPEAT_INTERVAL_SECONDS
        assert device.poll() == InputAction.DOWN
        assert device.decode_event(released_value, event_type, number) is None
        clock[0] += 1
        assert device.poll() is None
    finally:
        device.close()
