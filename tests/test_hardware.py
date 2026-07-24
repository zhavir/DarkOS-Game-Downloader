from pathlib import Path

from dw_cli.hardware import detect_hardware_profile


def write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)


def test_detects_device_tree_keys_and_framebuffer(tmp_path: Path) -> None:
    tree = tmp_path / "device-tree"
    graphics = tmp_path / "graphics"
    drm = tmp_path / "drm"
    write_bytes(tree / "model", b"R36S Test Board\0")
    write_bytes(tree / "compatible", b"rockchip,rk3326-r36s\0rockchip,rk3326\0")
    write_bytes(tree / "gpio-keys" / "compatible", b"gpio-keys\0")
    write_bytes(tree / "gpio-keys" / "button-up" / "label", b"D-pad Up\0")
    write_bytes(tree / "gpio-keys" / "button-up" / "linux,code", (103).to_bytes(4, "big"))
    write_bytes(tree / "adc-joystick" / "compatible", b"adc-joystick\0")
    write_bytes(graphics / "fb0" / "virtual_size", b"640,480\n")
    write_bytes(graphics / "fb0" / "name", b"rockchipdrmfb\n")

    profile = detect_hardware_profile(
        device_tree_roots=(tree,),
        graphics_root=graphics,
        drm_root=drm,
    )

    assert profile.model == "R36S Test Board"
    assert profile.compatible == ("rockchip,rk3326-r36s", "rockchip,rk3326")
    assert {item.node for item in profile.input_nodes} == {"/adc-joystick", "/gpio-keys"}
    assert len(profile.keys) == 1
    assert profile.keys[0].label == "D-pad Up"
    assert profile.keys[0].code == 103
    assert profile.keys[0].node == "/gpio-keys/button-up"
    assert profile.display_resolution == "640x480"
    assert profile.framebuffer_name == "rockchipdrmfb"


def test_drm_mode_is_used_when_framebuffer_size_is_unavailable(tmp_path: Path) -> None:
    tree = tmp_path / "missing-device-tree"
    graphics = tmp_path / "graphics"
    drm = tmp_path / "drm"
    write_bytes(drm / "card0-DSI-1" / "modes", b"720x480\n640x480\n")

    profile = detect_hardware_profile(
        device_tree_roots=(tree,),
        graphics_root=graphics,
        drm_root=drm,
    )

    assert profile.model == "unknown"
    assert profile.device_tree_root is None
    assert profile.display_resolution == "720x480"
    assert profile.display_source is not None
    assert profile.display_source.endswith("/card0-DSI-1/modes")


def test_invalid_properties_are_ignored(tmp_path: Path) -> None:
    tree = tmp_path / "device-tree"
    graphics = tmp_path / "graphics"
    write_bytes(tree / "gpio-keys" / "compatible", b"gpio-keys\0")
    write_bytes(tree / "gpio-keys" / "broken" / "linux,code", b"\x00\x01")
    write_bytes(graphics / "fb0" / "virtual_size", b"not-a-resolution")

    profile = detect_hardware_profile(
        device_tree_roots=(tree,),
        graphics_root=graphics,
        drm_root=tmp_path / "drm",
    )

    assert profile.keys == ()
    assert profile.display_resolution == "not detected"
