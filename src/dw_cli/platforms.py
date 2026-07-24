"""dArkOS platform metadata for RK3326-based R36S handhelds."""

from collections.abc import Iterable, Sequence
from pathlib import Path

from dw_cli.compatibility import is_unsupported_system
from dw_cli.models import Platform


def _platform(
    name: str,
    slug: str,
    alias: str,
    folder: str,
    code: str = "",
    *alternate_folders: str,
) -> Platform:
    return Platform(name, slug, code, alias, folder, alternate_folders)


# The folders follow the dArkOS R36S EmulationStation layout. Platforms explicitly
# limited to faster RK3566 devices (CD-i, GameCube and Tiger LCD) are intentionally
# omitted from this R36S/RK3326 profile. Empty service codes use the remote site's
# all-platform search while still installing into the exact dArkOS destination.
PLATFORMS: tuple[Platform, ...] = (
    Platform("All platforms", "all", "", "ALL"),
    _platform("3DO", "3do", "3DO", "3do"),
    _platform("Adventure Vision", "adventure-vision", "ADV", "advision"),
    _platform("American Laser Games", "american-laser-games", "ALG", "alg"),
    _platform("Amiga", "amiga", "AMIGA", "amiga"),
    _platform("Amiga CD32", "amiga-cd32", "CD32", "amigacd32"),
    _platform("Amstrad CPC", "amstrad-cpc", "CPC", "amstradcpc"),
    _platform("Amstrad GX4000", "amstrad-gx4000", "GX4000", "gx4000"),
    _platform("Apple II", "apple-ii", "APPLE2", "apple2"),
    _platform("Apple Macintosh", "apple-macintosh", "MAC", "vmac"),
    _platform("Aquaplus P/ECE", "aquaplus-piece", "PIECE", "piece"),
    _platform("Arcade", "arcade", "ARCADE", "arcade"),
    _platform("Arduboy", "arduboy", "ARDUBOY", "arduboy"),
    _platform("Astrocade", "astrocade", "ASTRO", "astrocde"),
    _platform("Atomiswave", "atomiswave", "ATOM", "atomiswave"),
    _platform("Atari 800", "atari-800", "A800", "atari800"),
    _platform("Atari 2600", "atari-2600", "A2600", "atari2600", "Atari2600"),
    _platform("Atari 5200", "atari-5200", "A5200", "atari5200", "Atari5200"),
    _platform("Atari 7800", "atari-7800", "A7800", "atari7800", "Atari7800"),
    _platform("Atari Jaguar", "atari-jaguar", "JAG", "atarijaguar", "Jaguar"),
    _platform("Atari Lynx", "atari-lynx", "LYNX", "atarilynx", "Lynx"),
    _platform("Atari ST", "atari-st", "AST", "atarist"),
    _platform("Atari XEGS", "atari-xegs", "XEGS", "atarixegs"),
    _platform("ColecoVision", "colecovision", "COLECO", "coleco"),
    _platform("Commodore 16", "commodore-16", "C16", "c16"),
    _platform("Commodore 64 / PET", "commodore-64", "C64", "c64"),
    _platform("Commodore 128", "commodore-128", "C128", "c128"),
    _platform("Commodore VIC-20", "commodore-vic-20", "VIC20", "vic20"),
    _platform("Capcom Play System I", "cps-1", "CPS1", "cps1"),
    _platform("Capcom Play System II", "cps-2", "CPS2", "cps2"),
    _platform("Capcom Play System III", "cps-3", "CPS3", "cps3"),
    _platform("Daphne", "daphne", "DAPHNE", "daphne"),
    _platform("Doom", "doom", "DOOM", "doom"),
    _platform("Dreamcast", "dreamcast", "DC", "dreamcast", "Dreamcast"),
    _platform("Dreamcast VMU", "dreamcast-vmu", "VMU", "vmu"),
    _platform("EasyRPG", "easyrpg", "EASYRPG", "easyrpg"),
    _platform("Enterprise 64/128", "enterprise", "EP64", "enterprise"),
    _platform("Fairchild Channel F", "fairchild-channel-f", "CHF", "channelf"),
    _platform("Famicom Disk System", "famicom-disk-system", "FDS", "fds"),
    _platform("Game Boy", "game-boy", "GB", "gb", "GB"),
    _platform("Game Boy Advance", "game-boy-advance", "GBA", "gba", "GBA"),
    _platform("Game & Watch", "game-and-watch", "GW", "gameandwatch"),
    _platform("Game Boy Color", "game-boy-color", "GBC", "gbc", "GBC"),
    _platform("Game Gear", "game-gear", "GG", "gamegear", "GG"),
    _platform("Genesis / Mega Drive", "genesis", "GEN", "megadrive", "Genesis", "genesis"),
    _platform("Intellivision", "intellivision", "INTV", "intellivision"),
    _platform("LÖVE", "love2d", "LOVE", "love2d"),
    _platform("LowRes NX", "lowres-nx", "LRNX", "lowresnx"),
    _platform("MAME 2003", "mame-2003", "MAME03", "mame2003"),
    _platform("MAME 2010", "mame-2010", "MAME", "mame"),
    _platform("Master System", "master-system", "SMS", "mastersystem", "SMS"),
    _platform("Mega Drive MSU", "megadrive-msu", "MSUMD", "msumd"),
    _platform("Mega Duck", "mega-duck", "MDUCK", "megaduck"),
    _platform("Microvision", "microvision", "MV", "mv"),
    _platform("MSX", "msx", "MSX", "msx"),
    _platform("MSX2", "msx2", "MSX2", "msx2"),
    _platform("Naomi", "naomi", "NAOMI", "naomi"),
    _platform("Neo Geo", "neo-geo", "NEOGEO", "neogeo"),
    _platform("Neo Geo CD", "neo-geo-cd", "NGCD", "neogeocd"),
    _platform("Neo Geo Pocket", "neo-geo-pocket", "NGP", "ngp"),
    _platform("Neo Geo Pocket Color", "neo-geo-pocket-color", "NGPC", "ngpc"),
    _platform("Nintendo 64", "nintendo-64", "N64", "n64", "N64"),
    _platform("Nintendo 64DD", "nintendo-64dd", "N64DD", "n64dd"),
    _platform("Nintendo DS", "nintendo-ds", "NDS", "nds", "DS"),
    _platform("Nintendo Entertainment System", "nintendo", "NES", "nes", "NES", "famicom"),
    _platform("Odyssey²", "odyssey-2", "O2", "odyssey2"),
    _platform("OpenBOR", "openbor", "OPENBOR", "openbor"),
    _platform("Palm OS", "palm-os", "PALM", "palm"),
    _platform("PC-98", "pc-98", "PC98", "pc98"),
    _platform("PC / MS-DOS", "dos", "DOS", "dos"),
    _platform("PC Engine / TurboGrafx-16", "pc-engine", "PCE", "pcengine", "TG16", "turbografx"),
    _platform(
        "PC Engine CD / TurboGrafx-CD",
        "pc-engine-cd",
        "PCECD",
        "pcenginecd",
        "TGCD",
        "turbografxcd",
    ),
    _platform("PC-FX", "pc-fx", "PCFX", "pcfx"),
    _platform("PICO-8", "pico-8", "PICO8", "pico-8/carts"),
    _platform("PlayStation", "playstation", "PS1", "psx", "PS1"),
    _platform("PlayStation Portable", "ps-portable", "PSP", "psp", "PSP"),
    _platform("PSP Minis", "psp-minis", "PSPM", "pspminis"),
    _platform("Pokémon Mini", "pokemon-mini", "PKMINI", "pokemonmini"),
    _platform("PuzzleScript", "puzzlescript", "PUZZLE", "puzzlescript"),
    _platform("Satellaview", "satellaview", "BSX", "satellaview"),
    _platform("ScummVM", "scummvm", "SCUMM", "scummvm"),
    _platform("Sega 32X", "sega-32x", "32X", "sega32x", "32X"),
    _platform("Sega CD", "sega-cd", "SCD", "segacd", "SegaCD"),
    _platform("Sega Pico", "sega-pico", "PICO", "pico"),
    _platform("Sega Saturn", "saturn", "SAT", "saturn", "Saturn"),
    _platform("SG-1000", "sg-1000", "SG1K", "sg-1000"),
    _platform("Sharp X1", "sharp-x1", "X1", "x1"),
    _platform("Sharp X68000", "sharp-x68000", "X68K", "x68000"),
    _platform("Solarus", "solarus", "SOLARUS", "solarus"),
    _platform("SuFami Turbo", "sufami-turbo", "SUFAMI", "sufami"),
    _platform("Super Cassette Vision", "super-cassette-vision", "SCV", "scv"),
    _platform("Super Game Boy", "super-game-boy", "SGB", "sgb"),
    _platform("SuperGrafx", "supergrafx", "SGFX", "supergrafx"),
    _platform("Super Nintendo", "super-nintendo", "SNES", "snes", "SNES", "sfc"),
    _platform("Super Nintendo MSU1", "super-nintendo-msu1", "MSU1", "snesmsu1"),
    _platform("Super Nintendo Hacks", "super-nintendo-hacks", "SNESH", "snes-hacks"),
    _platform("Tandy Color Computer 3", "coco-3", "COCO3", "coco3"),
    _platform("Thomson", "thomson", "THOM", "thomson"),
    _platform("TIC-80", "tic-80", "TIC80", "tic80"),
    _platform("TI-99/4A", "ti-99", "TI99", "ti99"),
    _platform("Uzebox", "uzebox", "UZE", "uzebox"),
    _platform("Vectrex", "vectrex", "VECT", "vectrex"),
    _platform("Videopac", "videopac", "VIDPAC", "videopac"),
    _platform("Videoton TV-Computer", "videoton-tvc", "TVC", "tvc"),
    _platform("Vircon32", "vircon32", "V32", "vircon32"),
    _platform("Virtual Boy", "virtual-boy", "VB", "virtualboy", "VB"),
    _platform("ONScripter", "onscripter", "ONS", "onscripter"),
    _platform("WASM-4", "wasm-4", "WASM4", "wasm4"),
    _platform("Watara Supervision", "watara-supervision", "SUPERV", "supervision"),
    _platform("Wolfenstein", "wolfenstein", "WOLF", "wolf"),
    _platform("WonderSwan", "wonderswan", "WS", "wonderswan"),
    _platform("WonderSwan Color", "wonderswan-color", "WSC", "wonderswancolor"),
    _platform("ZX81", "zx81", "ZX81", "zx81"),
    _platform("ZX Spectrum", "zx-spectrum", "ZXS", "zxspectrum"),
    _platform("Ports", "ports", "PORTS", "ports"),
)

NON_PLATFORM_DIRECTORIES = {
    "backup",
    "bios",
    "bgmusic",
    "downloads",
    "launchimages",
    "lost+found",
    "movies",
    "screensavers",
    "splash",
    "themes",
    "tools",
    "videos",
}


def discover_platforms(
    roms_directories: Iterable[Path], known: Sequence[Platform] = PLATFORMS
) -> tuple[Platform, ...]:
    """Add image-specific ROM folders found on SD1 or SD2 to the known set."""

    discovered = list(known)
    known_roots = {
        folder.split("/", maxsplit=1)[0].casefold()
        for platform in known
        for folder in platform.arkos_folders
    }
    custom_names: set[str] = set()
    for root in roms_directories:
        try:
            folders = tuple(path for path in root.iterdir() if path.is_dir())
        except OSError:
            continue
        for folder in folders:
            folded = folder.name.casefold()
            if (
                folded.startswith(".")
                or folded in known_roots
                or folded in NON_PLATFORM_DIRECTORIES
                or is_unsupported_system(folder.name)
            ):
                continue
            custom_names.add(folder.name)
    for name in sorted(custom_names, key=str.casefold):
        discovered.append(
            Platform(
                name=f"Detected: {name}",
                slug=f"detected-{name.casefold()}",
                code="",
                alias=name,
                arkos_folder=name,
            )
        )
    return tuple(discovered)


def _build_aliases() -> dict[str, Platform]:
    aliases: dict[str, Platform] = {}
    for platform in PLATFORMS:
        values = (
            platform.name,
            platform.slug,
            platform.alias,
            platform.code,
            *platform.arkos_folders,
        )
        for value in values:
            if value:
                aliases[value.casefold()] = platform
    return aliases


_ALIASES = _build_aliases()


def resolve_platform(value: str) -> Platform | None:
    """Resolve a slug, code, short alias, or dArkOS folder case-insensitively."""

    return _ALIASES.get(value.strip().casefold())
