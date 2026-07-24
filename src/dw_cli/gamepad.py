"""Direct Linux joystick input for dArkOS R36S controls."""

import os
import struct
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from time import monotonic


class InputAction(Enum):
    """Logical actions understood by the terminal UI."""

    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    SELECT = "select"
    BACK = "back"
    BACKSPACE = "backspace"
    SPACE = "space"
    PAGE_UP = "page_up"
    PAGE_DOWN = "page_down"
    START = "start"


JS_EVENT_BUTTON = 0x01
JS_EVENT_AXIS = 0x02
JS_EVENT_INIT = 0x80
AXIS_THRESHOLD = 16_000
EVENT_STRUCT = struct.Struct("IhBB")
REPEAT_DELAY_SECONDS = 0.35
REPEAT_INTERVAL_SECONDS = 0.08
REPEAT_ACTIONS = frozenset((InputAction.UP, InputAction.DOWN))

BUTTON_ACTIONS: dict[int, InputAction] = {
    0: InputAction.BACK,
    1: InputAction.SELECT,
    2: InputAction.BACKSPACE,
    3: InputAction.SPACE,
    4: InputAction.PAGE_UP,
    5: InputAction.PAGE_DOWN,
    # The R36S exists with two common dArkOS/ArkOS controller layouts.  Keep
    # both Select/Start pairs so the native joydev reader works on either DTB.
    6: InputAction.BACK,
    7: InputAction.START,
    8: InputAction.BACK,
    9: InputAction.START,
    14: InputAction.UP,
    15: InputAction.DOWN,
    16: InputAction.LEFT,
    17: InputAction.RIGHT,
}
# Linux joydev commonly exposes X/Y on 0/1, Z or RX on 2/3, RY on 4, and the
# D-pad hat on 6/7. This also covers dArkOS device-tree variants where the right
# stick is reported as RX/RY rather than the older Z/RX pairing.
HORIZONTAL_AXES = {0, 2, 6}
VERTICAL_AXES = {1, 3, 4, 7}


@dataclass(slots=True)
class LinuxJoystick:
    """Non-blocking reader for Linux's stable ``/dev/input/js*`` interface."""

    path: Path
    _file_descriptor: int
    _axis_state: dict[int, int] = field(default_factory=dict)
    _pending: deque[InputAction] = field(default_factory=deque)
    _repeat_action: InputAction | None = None
    _repeat_due_at: float = 0.0

    @classmethod
    def open_first(cls, input_directory: Path = Path("/dev/input")) -> LinuxJoystick | None:
        """Open the first readable joystick, normally the R36S built-in controls."""

        for path in sorted(input_directory.glob("js*")):
            try:
                descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                continue
            return cls(path=path, _file_descriptor=descriptor)
        return None

    def poll(self) -> InputAction | None:
        """Return the next available action without blocking the TUI."""

        if self._pending:
            return self._pending.popleft()
        try:
            payload = os.read(self._file_descriptor, EVENT_STRUCT.size * 16)
        except BlockingIOError:
            return self._poll_repeat()
        except OSError:
            self.close()
            return None

        for offset in range(0, len(payload) - EVENT_STRUCT.size + 1, EVENT_STRUCT.size):
            _timestamp, value, event_type, number = EVENT_STRUCT.unpack_from(payload, offset)
            action = self.decode_event(value, event_type, number)
            if action is not None:
                self._pending.append(action)
        return self._pending.popleft() if self._pending else self._poll_repeat()

    def decode_event(self, value: int, event_type: int, number: int) -> InputAction | None:
        """Translate one js event; public to allow device-independent tests."""

        if event_type & JS_EVENT_INIT:
            return None
        kind = event_type & ~JS_EVENT_INIT
        if kind == JS_EVENT_BUTTON:
            action = BUTTON_ACTIONS.get(number)
            if action not in REPEAT_ACTIONS:
                return action if value else None
            if value:
                self._start_repeat(action)
                return action
            self._stop_repeat(action)
            return None
        if kind != JS_EVENT_AXIS:
            return None

        direction = -1 if value < -AXIS_THRESHOLD else 1 if value > AXIS_THRESHOLD else 0
        previous = self._axis_state.get(number, 0)
        self._axis_state[number] = direction
        previous_action = self._axis_action(number, previous)
        if direction == 0:
            self._stop_repeat(previous_action)
            return None
        if direction == previous:
            return None
        action = self._axis_action(number, direction)
        self._stop_repeat(previous_action)
        if action in REPEAT_ACTIONS:
            self._start_repeat(action)
        return action

    @staticmethod
    def _axis_action(number: int, direction: int) -> InputAction | None:
        if not direction:
            return None
        if number in HORIZONTAL_AXES:
            return InputAction.LEFT if direction < 0 else InputAction.RIGHT
        if number in VERTICAL_AXES:
            return InputAction.UP if direction < 0 else InputAction.DOWN
        return None

    def _start_repeat(self, action: InputAction) -> None:
        self._repeat_action = action
        self._repeat_due_at = monotonic() + REPEAT_DELAY_SECONDS

    def _stop_repeat(self, action: InputAction | None) -> None:
        if action is not None and action == self._repeat_action:
            self._repeat_action = None
            self._repeat_due_at = 0.0

    def _poll_repeat(self) -> InputAction | None:
        if self._repeat_action is None or monotonic() < self._repeat_due_at:
            return None
        self._repeat_due_at = monotonic() + REPEAT_INTERVAL_SECONDS
        return self._repeat_action

    def close(self) -> None:
        """Release the device descriptor, tolerating repeated calls."""

        if self._file_descriptor < 0:
            return
        try:
            os.close(self._file_descriptor)
        finally:
            self._file_descriptor = -1
