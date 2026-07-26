"""Read safe runtime hardware facts exposed by the Linux kernel."""

from dataclasses import dataclass
from pathlib import Path

DEFAULT_DEVICE_TREE_ROOTS = (
    Path("/proc/device-tree"),
    Path("/sys/firmware/devicetree/base"),
)
DEFAULT_GRAPHICS_ROOT = Path("/sys/class/graphics")
DEFAULT_DRM_ROOT = Path("/sys/class/drm")
MAX_PROPERTY_BYTES = 64 * 1024
INPUT_COMPATIBLE_MARKERS = ("gamepad", "gpio-keys", "joystick")


@dataclass(frozen=True, slots=True)
class DeviceTreeKey:
    """One Linux input key declared by a device-tree node."""

    label: str
    code: int
    node: str


@dataclass(frozen=True, slots=True)
class DeviceTreeInput:
    """A device-tree input-related node useful for diagnostics."""

    node: str
    compatible: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HardwareProfile:
    """Hardware facts that are useful to the handheld UI and its log."""

    model: str = "unknown"
    compatible: tuple[str, ...] = ()
    device_tree_root: str | None = None
    input_nodes: tuple[DeviceTreeInput, ...] = ()
    keys: tuple[DeviceTreeKey, ...] = ()
    display_width: int | None = None
    display_height: int | None = None
    display_source: str | None = None
    framebuffer_name: str | None = None

    @property
    def display_resolution(self) -> str:
        """Return a compact pixel resolution for display in the TUI."""

        if self.display_width is None or self.display_height is None:
            return "not detected"
        return f"{self.display_width}x{self.display_height}"


def detect_hardware_profile(
    *,
    device_tree_roots: tuple[Path, ...] = DEFAULT_DEVICE_TREE_ROOTS,
    graphics_root: Path = DEFAULT_GRAPHICS_ROOT,
    drm_root: Path = DEFAULT_DRM_ROOT,
) -> HardwareProfile:
    """Inspect the kernel's live device tree and display class attributes."""

    device_tree_root = next((root for root in device_tree_roots if root.is_dir()), None)
    model = "unknown"
    compatible: tuple[str, ...] = ()
    input_nodes: tuple[DeviceTreeInput, ...] = ()
    keys: tuple[DeviceTreeKey, ...] = ()
    if device_tree_root is not None:
        model_values = _read_strings(device_tree_root / "model")
        if model_values:
            model = model_values[0]
        compatible = _read_strings(device_tree_root / "compatible")
        input_nodes = _find_input_nodes(device_tree_root)
        keys = _find_gpio_keys(device_tree_root, input_nodes)

    display_width, display_height, display_source, framebuffer_name = _detect_display(
        graphics_root,
        drm_root,
    )
    profile = HardwareProfile(
        model=model,
        compatible=compatible,
        device_tree_root=str(device_tree_root) if device_tree_root is not None else None,
        input_nodes=input_nodes,
        keys=keys,
        display_width=display_width,
        display_height=display_height,
        display_source=display_source,
        framebuffer_name=framebuffer_name,
    )
    return profile


def _find_input_nodes(root: Path) -> tuple[DeviceTreeInput, ...]:
    inputs: list[DeviceTreeInput] = []
    try:
        compatible_paths = sorted(root.rglob("compatible"))
    except OSError:
        return ()
    for compatible_path in compatible_paths:
        compatible = _read_strings(compatible_path)
        searchable = " ".join((compatible_path.parent.name, *compatible)).casefold()
        if not any(marker in searchable for marker in INPUT_COMPATIBLE_MARKERS):
            continue
        inputs.append(
            DeviceTreeInput(
                node=_relative_node(compatible_path.parent, root),
                compatible=compatible,
            )
        )
    return tuple(inputs)


def _find_gpio_keys(
    root: Path,
    input_nodes: tuple[DeviceTreeInput, ...],
) -> tuple[DeviceTreeKey, ...]:
    keys: list[DeviceTreeKey] = []
    gpio_node_names = {
        item.node
        for item in input_nodes
        if any("gpio-keys" in value.casefold() for value in item.compatible)
    }
    for node_name in sorted(gpio_node_names):
        node = root if node_name == "/" else root / node_name.removeprefix("/")
        try:
            code_paths = sorted(node.rglob("linux,code"))
        except OSError:
            continue
        for code_path in code_paths:
            code = _read_u32(code_path)
            if code is None:
                continue
            labels = _read_strings(code_path.parent / "label")
            keys.append(
                DeviceTreeKey(
                    label=labels[0] if labels else code_path.parent.name,
                    code=code,
                    node=_relative_node(code_path.parent, root),
                )
            )
    return tuple(keys)


def _detect_display(
    graphics_root: Path,
    drm_root: Path,
) -> tuple[int | None, int | None, str | None, str | None]:
    for virtual_size in sorted(graphics_root.glob("fb*/virtual_size")):
        resolution = _parse_resolution(_read_text(virtual_size))
        if resolution is None:
            continue
        framebuffer_name = _read_text(virtual_size.parent / "name") or None
        return (*resolution, str(virtual_size), framebuffer_name)

    for modes_path in sorted(drm_root.glob("card*-*/modes")):
        modes = _read_text(modes_path).splitlines()
        if not modes:
            continue
        resolution = _parse_resolution(modes[0])
        if resolution is not None:
            return (*resolution, str(modes_path), None)
    return (None, None, None, None)


def _parse_resolution(value: str) -> tuple[int, int] | None:
    normalized = value.strip().lower().replace(",", "x")
    pieces = normalized.split("x", maxsplit=1)
    if len(pieces) != 2:
        return None
    try:
        width, height = (int(piece) for piece in pieces)
    except ValueError:
        return None
    if width <= 0 or height <= 0:
        return None
    return (width, height)


def _read_bytes(path: Path) -> bytes:
    try:
        with path.open("rb") as stream:
            return stream.read(MAX_PROPERTY_BYTES)
    except OSError:
        return b""


def _read_strings(path: Path) -> tuple[str, ...]:
    return tuple(
        item.decode("utf-8", errors="replace").strip()
        for item in _read_bytes(path).split(b"\0")
        if item
    )


def _read_text(path: Path) -> str:
    return _read_bytes(path).decode("utf-8", errors="replace").strip("\0\r\n ")


def _read_u32(path: Path) -> int | None:
    value = _read_bytes(path)
    if len(value) != 4:
        return None
    return int.from_bytes(value, byteorder="big")


def _relative_node(path: Path, root: Path) -> str:
    relative = path.relative_to(root).as_posix()
    return "/" if relative == "." else f"/{relative}"
