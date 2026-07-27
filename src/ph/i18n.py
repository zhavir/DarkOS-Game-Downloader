"""Small offline translation catalogue for the controller-driven interface."""

from dataclasses import dataclass
from string import Formatter
from typing import Literal

type LanguageCode = Literal["en", "de", "es", "it", "pt"]

DEFAULT_LANGUAGE: LanguageCode = "en"


@dataclass(frozen=True, slots=True)
class Language:
    """One selectable interface language."""

    code: LanguageCode
    name: str


LANGUAGES: tuple[Language, ...] = (
    Language("en", "English"),
    Language("de", "Deutsch"),
    Language("es", "Español"),
    Language("it", "Italiano"),
    Language("pt", "Português"),
)

_ENGLISH: dict[str, str] = {
    "app_title": "POCKET HARBOR",
    "search_library": "Search the library",
    "direct_download": "Download from a detail link",
    "download_queue": "Downloads",
    "manage_games": "Manage installed games",
    "search_bios": "Search and download BIOS",
    "settings": "Settings",
    "status_controls": "System status and controls",
    "exit": "Exit",
    "main_footer": "D-pad/stick: move   A/Enter: select",
    "back": "Back",
    "cancel": "Cancel",
    "download": "Download",
    "true": "True",
    "false": "False",
    "language": "Language",
    "choose_language": "CHOOSE LANGUAGE",
    "language_footer": "The selected language applies immediately",
    "language_saved": "LANGUAGE SAVED",
    "language_saved_message": "The interface language is now {language}.",
    "choose_platform": "CHOOSE A PLATFORM",
    "back_footer": "B/Escape: back",
    "search_title": "SEARCH {platform}",
    "search_empty_hint": "DONE with no text: list all games",
    "searching": "SEARCHING",
    "looking_for": "Looking for {query}...",
    "loading_all": "Loading all {platform} games...",
    "no_results": "NO RESULTS",
    "nothing_matched": "Nothing matched {query}.",
    "catalogue_empty": "The catalogue is empty.",
    "checking_compatibility": "CHECKING COMPATIBILITY",
    "matching_compatibility": "Matching results against the cached compatibility catalogue...",
    "results_title": "{store} RESULTS ({count})",
    "results_footer": "A/Enter: details   B/Escape: back",
    "title_details": "TITLE DETAILS",
    "select_download": "Choose Download to continue",
    "system_field": "System: {value}",
    "region_field": "Region: {value}",
    "version_field": "Version: {value}",
    "languages_field": "Languages: {value}",
    "rating_field": "Rating: {value}",
    "compatibility_field": "Compatibility: {value}",
    "compatibility_badge": "Compatibility: {value}",
    "settings_title": "SETTINGS",
    "settings_footer": "Store, interface, cache, logging, and application settings",
    "change_store": "Change download store  [current: {value}]",
    "refresh_store_cache": "Refresh store game catalogue  [{count} cached]",
    "update_bios_catalogue": "Update RetroBIOS catalogue  [{status}]",
    "update_compatibility": "Update compatibility catalogue  [{status}]",
    "cache_lifetime": "Catalogue cache lifetime  [{days} days]",
    "max_concurrent_downloads": "Concurrent downloads  [{count}]",
    "max_concurrent_downloads_title": "MAXIMUM CONCURRENT DOWNLOADS",
    "max_concurrent_downloads_hint": "Current value: {current}; allowed range: 1-8",
    "max_concurrent_downloads_range": "Enter a whole number from 1 to 8.",
    "max_concurrent_downloads_saved": "DOWNLOAD LIMIT SAVED",
    "max_concurrent_downloads_saved_message": (
        "Up to {count} downloads will run at once after Pocket Harbor is restarted."
    ),
    "rate_limit_retry_settings": "Rate-limit retry settings",
    "rate_limit_retry_title": "RATE-LIMIT RETRY SETTINGS",
    "rate_limit_retry_footer": "Changes apply to retry delays scheduled from now on",
    "rate_limit_retry_base": "Initial delay  [{value:g} seconds]",
    "rate_limit_retry_max": "Maximum delay  [{value:g} seconds]",
    "rate_limit_retry_jitter": "Random jitter  [{value:g}%]",
    "rate_limit_retry_base_seconds_title": "INITIAL RETRY DELAY (SECONDS)",
    "rate_limit_retry_max_seconds_title": "MAXIMUM RETRY DELAY (SECONDS)",
    "rate_limit_retry_jitter_ratio_title": "RETRY JITTER (PERCENT)",
    "rate_limit_retry_invalid": (
        "Use 1-3600 seconds initially, up to 86400 seconds maximum, and 0-100% jitter. "
        "The maximum must not be shorter than the initial delay."
    ),
    "rate_limit_retry_saved": "RETRY SETTINGS SAVED",
    "rate_limit_retry_saved_message": "New rate-limit retries will use these values.",
    "log_level": "Application log level  [{value}]",
    "file_logging": "Write logs to file  [{value}]",
    "minerva_settings": "Minerva BitTorrent settings",
    "check_update": "Check for application update  [installed: v{version}]",
    "not_set": "not set",
    "on": "on",
    "off": "off",
    "cache_days_title": "CATALOGUE CACHE DAYS",
    "cache_days_hint": "Current: {current}; default: {default}",
    "cache_lifetime_saved": "CACHE LIFETIME SAVED",
    "cache_lifetime_saved_message": "Catalogue files now expire after {days} day(s).",
    "invalid_cache_lifetime": "Invalid catalogue lifetime: {error}",
    "log_level_title": "APPLICATION LOG LEVEL",
    "log_level_footer": "The selected level applies immediately",
    "log_level_saved": "LOG LEVEL SAVED",
    "log_level_saved_message": "Application logging is now set to {level}.",
    "file_logging_title": "WRITE LOGS TO FILE?",
    "file_logging_footer": "Changes apply immediately and are saved for the next launch",
    "file_logging_saved": "FILE LOGGING SAVED",
    "file_logging_enabled": "File logging is enabled at:\n{path}",
    "file_logging_failed": (
        "File logging could not be enabled. Check write access to the tool folder."
    ),
    "file_logging_disabled": "File logging is disabled.",
    "integer_keyboard": "Numbers only",
    "float_keyboard": "Numbers and decimal point only",
    "mixed_keyboard": "Letters, numbers, and symbols",
    "keyboard_footer": "{page}   D-pad: move   A: key   X: confirm   Y: back   B: cancel",
    "space": "SPACE",
    "done": "DONE",
    "key_back": "BACK",
    "error": "ERROR",
    "continue_footer": "A/Enter/B/Escape: continue",
    "choose_store_catalogue": "CHOOSE STORE CATALOGUE",
    "choose_store_footer": "Select a store; B/Escape returns",
    "refresh_store_title": "REFRESH {store}",
    "refresh_store_footer": "This replaces the selected cache before its lifetime expires",
    "refreshing_catalogue": "REFRESHING GAME CATALOGUE",
    "refreshing_catalogue_message": "Downloading the complete {store} catalogue for {platform}...",
    "catalogue_updated": "GAME CATALOGUE UPDATED",
    "catalogue_updated_message": "Cached {count} {store} result(s) for {platform}.",
    "not_downloaded": "not downloaded",
    "fresh_games": "fresh, {count} games",
    "stale_games": "stale, {count} games",
    "compatibility_update_title": "UPDATE COMPATIBILITY CATALOGUE?",
    "compatibility_update_download": "Download latest compatibility catalogue",
    "keep_catalogue": "Keep current catalogue",
    "keep_cache_footer": "The existing offline cache is kept if the update fails",
    "compatibility_updating": "UPDATING COMPATIBILITY CATALOGUE",
    "compatibility_updating_message": "Downloading the current game compatibility catalogue...",
    "compatibility_updated": "COMPATIBILITY CATALOGUE UPDATED",
    "compatibility_updated_message": "Cached {count} game title(s). Valid for {days} day(s).",
    "automatic_update_package": (
        "Automatic updates are available from a self-contained package for the selected OS. "
        "Local development checkouts should update with git and uv."
    ),
}

_TRANSLATIONS: dict[LanguageCode, dict[str, str]] = {
    "en": _ENGLISH,
    "de": {
        "app_title": "POCKET HARBOR",
        "search_library": "Spielebibliothek durchsuchen",
        "direct_download": "Über einen Detaillink herunterladen",
        "download_queue": "Downloads",
        "manage_games": "Installierte Spiele verwalten",
        "search_bios": "BIOS suchen und herunterladen",
        "settings": "Einstellungen",
        "status_controls": "Systemstatus und Steuerung",
        "exit": "Beenden",
        "main_footer": "Steuerkreuz/Stick: bewegen   A/Enter: auswählen",
        "back": "Zurück",
        "cancel": "Abbrechen",
        "download": "Herunterladen",
        "true": "Wahr",
        "false": "Falsch",
        "language": "Sprache",
        "choose_language": "SPRACHE AUSWÄHLEN",
        "language_footer": "Die gewählte Sprache gilt sofort",
        "language_saved": "SPRACHE GESPEICHERT",
        "language_saved_message": "Die Sprache der Oberfläche ist jetzt {language}.",
        "choose_platform": "PLATTFORM AUSWÄHLEN",
        "back_footer": "B/Escape: zurück",
        "search_title": "{platform} DURCHSUCHEN",
        "search_empty_hint": "FERTIG ohne Text: alle Spiele anzeigen",
        "searching": "SUCHE",
        "looking_for": "Suche nach {query}...",
        "loading_all": "Alle Spiele für {platform} werden geladen...",
        "no_results": "KEINE ERGEBNISSE",
        "nothing_matched": "Keine Treffer für {query}.",
        "catalogue_empty": "Der Katalog ist leer.",
        "checking_compatibility": "KOMPATIBILITÄT WIRD GEPRÜFT",
        "matching_compatibility": (
            "Ergebnisse werden mit dem lokalen Kompatibilitätskatalog verglichen..."
        ),
        "results_title": "{store}: ERGEBNISSE ({count})",
        "results_footer": "A/Enter: Details   B/Escape: zurück",
        "title_details": "SPIELDETAILS",
        "select_download": "Zum Fortfahren Herunterladen wählen",
        "system_field": "System: {value}",
        "region_field": "Region: {value}",
        "version_field": "Version: {value}",
        "languages_field": "Sprachen: {value}",
        "rating_field": "Bewertung: {value}",
        "compatibility_field": "Kompatibilität: {value}",
        "compatibility_badge": "Kompatibilität: {value}",
        "settings_title": "EINSTELLUNGEN",
        "settings_footer": "Store-, Oberflächen-, Cache-, Protokoll- und App-Einstellungen",
        "change_store": "Download-Store ändern  [aktuell: {value}]",
        "refresh_store_cache": "Spielekatalog aktualisieren  [{count} gespeichert]",
        "update_bios_catalogue": "RetroBIOS-Katalog aktualisieren  [{status}]",
        "update_compatibility": "Kompatibilitätskatalog aktualisieren  [{status}]",
        "cache_lifetime": "Katalog-Cache-Dauer  [{days} Tage]",
        "max_concurrent_downloads": "Gleichzeitige Downloads  [{count}]",
        "max_concurrent_downloads_title": "MAXIMALE GLEICHZEITIGE DOWNLOADS",
        "max_concurrent_downloads_hint": "Aktueller Wert: {current}; erlaubter Bereich: 1-8",
        "max_concurrent_downloads_range": "Geben Sie eine ganze Zahl von 1 bis 8 ein.",
        "max_concurrent_downloads_saved": "DOWNLOAD-LIMIT GESPEICHERT",
        "max_concurrent_downloads_saved_message": (
            "Nach dem Neustart laufen bis zu {count} Downloads gleichzeitig."
        ),
        "rate_limit_retry_settings": "Einstellungen für Rate-Limit-Wiederholungen",
        "rate_limit_retry_title": "RATE-LIMIT-WIEDERHOLUNGEN",
        "rate_limit_retry_footer": "Änderungen gelten für neu geplante Versuche",
        "rate_limit_retry_base": "Anfangsverzögerung  [{value:g} Sekunden]",
        "rate_limit_retry_max": "Maximale Verzögerung  [{value:g} Sekunden]",
        "rate_limit_retry_jitter": "Zufällige Streuung  [{value:g}%]",
        "rate_limit_retry_base_seconds_title": "ANFANGSVERZÖGERUNG (SEKUNDEN)",
        "rate_limit_retry_max_seconds_title": "MAXIMALE VERZÖGERUNG (SEKUNDEN)",
        "rate_limit_retry_jitter_ratio_title": "ZUFÄLLIGE STREUUNG (PROZENT)",
        "rate_limit_retry_invalid": (
            "Anfang 1-3600 Sekunden, Maximum bis 86400 Sekunden und Streuung 0-100%. "
            "Das Maximum darf nicht kürzer als der Anfang sein."
        ),
        "rate_limit_retry_saved": "WIEDERHOLUNGSEINSTELLUNGEN GESPEICHERT",
        "rate_limit_retry_saved_message": "Neue Rate-Limit-Versuche verwenden diese Werte.",
        "log_level": "Protokollstufe  [{value}]",
        "file_logging": "In Datei protokollieren  [{value}]",
        "minerva_settings": "Minerva-BitTorrent-Einstellungen",
        "check_update": "App-Update suchen  [installiert: v{version}]",
        "not_set": "nicht festgelegt",
        "on": "ein",
        "off": "aus",
        "cache_days_title": "KATALOG-CACHE IN TAGEN",
        "cache_days_hint": "Aktuell: {current}; Standard: {default}",
        "cache_lifetime_saved": "CACHE-DAUER GESPEICHERT",
        "cache_lifetime_saved_message": "Katalogdateien laufen nach {days} Tag(en) ab.",
        "invalid_cache_lifetime": "Ungültige Katalogdauer: {error}",
        "log_level_title": "PROTOKOLLSTUFE",
        "log_level_footer": "Die gewählte Stufe gilt sofort",
        "log_level_saved": "PROTOKOLLSTUFE GESPEICHERT",
        "log_level_saved_message": "Die Protokollstufe ist jetzt {level}.",
        "file_logging_title": "PROTOKOLL IN DATEI SCHREIBEN?",
        "file_logging_footer": "Die Änderung gilt sofort und wird gespeichert",
        "file_logging_saved": "DATEIPROTOKOLL GESPEICHERT",
        "file_logging_enabled": "Dateiprotokollierung ist hier aktiviert:\n{path}",
        "file_logging_failed": (
            "Das Dateiprotokoll konnte nicht aktiviert werden. Prüfen Sie die Schreibrechte."
        ),
        "file_logging_disabled": "Dateiprotokollierung ist deaktiviert.",
        "integer_keyboard": "Nur Zahlen",
        "float_keyboard": "Nur Zahlen und Dezimalpunkt",
        "mixed_keyboard": "Buchstaben, Zahlen und Symbole",
        "keyboard_footer": (
            "{page}   Steuerkreuz: bewegen   A: Taste   X: bestätigen   Y: zurück   B: abbrechen"
        ),
        "space": "LEER",
        "done": "FERTIG",
        "key_back": "ZURÜCK",
        "error": "FEHLER",
        "continue_footer": "A/Enter/B/Escape: weiter",
        "choose_store_catalogue": "STORE-KATALOG AUSWÄHLEN",
        "choose_store_footer": "Store auswählen; B/Escape: zurück",
        "refresh_store_title": "{store} AKTUALISIEREN",
        "refresh_store_footer": "Ersetzt den gewählten Cache vor Ablauf seiner Dauer",
        "refreshing_catalogue": "SPIELEKATALOG WIRD AKTUALISIERT",
        "refreshing_catalogue_message": (
            "Vollständiger {store}-Katalog für {platform} wird geladen..."
        ),
        "catalogue_updated": "SPIELEKATALOG AKTUALISIERT",
        "catalogue_updated_message": "{count} {store}-Ergebnis(se) für {platform} gespeichert.",
        "not_downloaded": "nicht heruntergeladen",
        "fresh_games": "aktuell, {count} Spiele",
        "stale_games": "veraltet, {count} Spiele",
        "compatibility_update_title": "KOMPATIBILITÄTSKATALOG AKTUALISIEREN?",
        "compatibility_update_download": "Neuesten Kompatibilitätskatalog laden",
        "keep_catalogue": "Aktuellen Katalog behalten",
        "keep_cache_footer": "Bei Fehler bleibt der vorhandene Offline-Cache erhalten",
        "compatibility_updating": "KOMPATIBILITÄTSKATALOG WIRD AKTUALISIERT",
        "compatibility_updating_message": "Aktueller Spiele-Kompatibilitätskatalog wird geladen...",
        "compatibility_updated": "KOMPATIBILITÄTSKATALOG AKTUALISIERT",
        "compatibility_updated_message": (
            "{count} Spieletitel gespeichert. Gültig für {days} Tag(e)."
        ),
        "automatic_update_package": (
            "Automatische Updates sind im eigenständigen Paket für das gewählte "
            "Betriebssystem verfügbar. "
            "Lokale Entwicklungsordner werden mit git und uv aktualisiert."
        ),
    },
    "es": {
        "app_title": "POCKET HARBOR",
        "search_library": "Buscar en la biblioteca",
        "direct_download": "Descargar desde un enlace",
        "download_queue": "Descargas",
        "manage_games": "Gestionar juegos instalados",
        "search_bios": "Buscar y descargar BIOS",
        "settings": "Ajustes",
        "status_controls": "Estado y controles del sistema",
        "exit": "Salir",
        "main_footer": "Cruceta/stick: mover   A/Enter: seleccionar",
        "back": "Atrás",
        "cancel": "Cancelar",
        "download": "Descargar",
        "true": "Verdadero",
        "false": "Falso",
        "language": "Idioma",
        "choose_language": "ELEGIR IDIOMA",
        "language_footer": "El idioma elegido se aplica inmediatamente",
        "language_saved": "IDIOMA GUARDADO",
        "language_saved_message": "El idioma de la interfaz ahora es {language}.",
        "choose_platform": "ELEGIR PLATAFORMA",
        "back_footer": "B/Escape: atrás",
        "search_title": "BUSCAR {platform}",
        "search_empty_hint": "HECHO sin texto: mostrar todos los juegos",
        "searching": "BUSCANDO",
        "looking_for": "Buscando {query}...",
        "loading_all": "Cargando todos los juegos de {platform}...",
        "no_results": "SIN RESULTADOS",
        "nothing_matched": "No hay resultados para {query}.",
        "catalogue_empty": "El catálogo está vacío.",
        "checking_compatibility": "COMPROBANDO COMPATIBILIDAD",
        "matching_compatibility": (
            "Comparando resultados con el catálogo de compatibilidad local..."
        ),
        "results_title": "RESULTADOS DE {store} ({count})",
        "results_footer": "A/Enter: detalles   B/Escape: atrás",
        "title_details": "DETALLES DEL JUEGO",
        "select_download": "Elige Descargar para continuar",
        "system_field": "Sistema: {value}",
        "region_field": "Región: {value}",
        "version_field": "Versión: {value}",
        "languages_field": "Idiomas: {value}",
        "rating_field": "Valoración: {value}",
        "compatibility_field": "Compatibilidad: {value}",
        "compatibility_badge": "Compatibilidad: {value}",
        "settings_title": "AJUSTES",
        "settings_footer": "Ajustes de tienda, interfaz, caché, registro y aplicación",
        "change_store": "Cambiar tienda  [actual: {value}]",
        "refresh_store_cache": "Actualizar catálogo de juegos  [{count} guardados]",
        "update_bios_catalogue": "Actualizar catálogo RetroBIOS  [{status}]",
        "update_compatibility": "Actualizar catálogo de compatibilidad  [{status}]",
        "cache_lifetime": "Duración de caché  [{days} días]",
        "max_concurrent_downloads": "Descargas simultáneas  [{count}]",
        "max_concurrent_downloads_title": "MÁXIMO DE DESCARGAS SIMULTÁNEAS",
        "max_concurrent_downloads_hint": "Valor actual: {current}; intervalo permitido: 1-8",
        "max_concurrent_downloads_range": "Introduce un número entero del 1 al 8.",
        "max_concurrent_downloads_saved": "LÍMITE DE DESCARGAS GUARDADO",
        "max_concurrent_downloads_saved_message": (
            "Tras reiniciar, se ejecutarán hasta {count} descargas simultáneas."
        ),
        "rate_limit_retry_settings": "Ajustes de reintento por límite",
        "rate_limit_retry_title": "REINTENTOS POR LÍMITE",
        "rate_limit_retry_footer": "Los cambios se aplican a los nuevos reintentos",
        "rate_limit_retry_base": "Espera inicial  [{value:g} segundos]",
        "rate_limit_retry_max": "Espera máxima  [{value:g} segundos]",
        "rate_limit_retry_jitter": "Variación aleatoria  [{value:g}%]",
        "rate_limit_retry_base_seconds_title": "ESPERA INICIAL (SEGUNDOS)",
        "rate_limit_retry_max_seconds_title": "ESPERA MÁXIMA (SEGUNDOS)",
        "rate_limit_retry_jitter_ratio_title": "VARIACIÓN ALEATORIA (PORCENTAJE)",
        "rate_limit_retry_invalid": (
            "Usa 1-3600 segundos al inicio, hasta 86400 segundos como máximo y 0-100% de "
            "variación. El máximo no puede ser menor que el inicial."
        ),
        "rate_limit_retry_saved": "AJUSTES DE REINTENTO GUARDADOS",
        "rate_limit_retry_saved_message": "Los nuevos reintentos usarán estos valores.",
        "log_level": "Nivel de registro  [{value}]",
        "file_logging": "Guardar registro en archivo  [{value}]",
        "minerva_settings": "Ajustes BitTorrent de Minerva",
        "check_update": "Buscar actualización  [instalada: v{version}]",
        "not_set": "sin configurar",
        "on": "sí",
        "off": "no",
        "cache_days_title": "DÍAS DE CACHÉ DEL CATÁLOGO",
        "cache_days_hint": "Actual: {current}; predeterminado: {default}",
        "cache_lifetime_saved": "DURACIÓN GUARDADA",
        "cache_lifetime_saved_message": "Los catálogos caducan después de {days} día(s).",
        "invalid_cache_lifetime": "Duración no válida: {error}",
        "log_level_title": "NIVEL DE REGISTRO",
        "log_level_footer": "El nivel elegido se aplica inmediatamente",
        "log_level_saved": "NIVEL GUARDADO",
        "log_level_saved_message": "El nivel de registro ahora es {level}.",
        "file_logging_title": "¿GUARDAR REGISTRO EN ARCHIVO?",
        "file_logging_footer": "El cambio se aplica ahora y se guarda",
        "file_logging_saved": "REGISTRO GUARDADO",
        "file_logging_enabled": "El registro está activado en:\n{path}",
        "file_logging_failed": (
            "No se pudo activar el registro. Comprueba los permisos de escritura."
        ),
        "file_logging_disabled": "El registro en archivo está desactivado.",
        "integer_keyboard": "Solo números",
        "float_keyboard": "Solo números y punto decimal",
        "mixed_keyboard": "Letras, números y símbolos",
        "keyboard_footer": (
            "{page}   Cruceta: mover   A: tecla   X: confirmar   Y: borrar   B: cancelar"
        ),
        "space": "ESPACIO",
        "done": "HECHO",
        "key_back": "BORRAR",
        "error": "ERROR",
        "continue_footer": "A/Enter/B/Escape: continuar",
        "choose_store_catalogue": "ELEGIR CATÁLOGO DE TIENDA",
        "choose_store_footer": "Elige una tienda; B/Escape: atrás",
        "refresh_store_title": "ACTUALIZAR {store}",
        "refresh_store_footer": "Sustituye la caché seleccionada antes de que caduque",
        "refreshing_catalogue": "ACTUALIZANDO CATÁLOGO DE JUEGOS",
        "refreshing_catalogue_message": (
            "Descargando el catálogo completo de {store} para {platform}..."
        ),
        "catalogue_updated": "CATÁLOGO DE JUEGOS ACTUALIZADO",
        "catalogue_updated_message": "Guardados {count} resultados de {store} para {platform}.",
        "not_downloaded": "no descargado",
        "fresh_games": "actual, {count} juegos",
        "stale_games": "caducado, {count} juegos",
        "compatibility_update_title": "¿ACTUALIZAR CATÁLOGO DE COMPATIBILIDAD?",
        "compatibility_update_download": "Descargar el catálogo de compatibilidad más reciente",
        "keep_catalogue": "Conservar el catálogo actual",
        "keep_cache_footer": "La caché existente se conserva si falla la actualización",
        "compatibility_updating": "ACTUALIZANDO COMPATIBILIDAD",
        "compatibility_updating_message": "Descargando el catálogo de compatibilidad actual...",
        "compatibility_updated": "CATÁLOGO DE COMPATIBILIDAD ACTUALIZADO",
        "compatibility_updated_message": "Guardados {count} títulos. Válido durante {days} día(s).",
        "automatic_update_package": (
            "Las actualizaciones automáticas están disponibles en el paquete autónomo para "
            "el sistema operativo elegido. Los entornos locales se actualizan con git y uv."
        ),
    },
    "it": {
        "app_title": "POCKET HARBOR",
        "search_library": "Cerca nella libreria",
        "direct_download": "Scarica da un link",
        "download_queue": "Download",
        "manage_games": "Gestisci i giochi installati",
        "search_bios": "Cerca e scarica BIOS",
        "settings": "Impostazioni",
        "status_controls": "Stato e controlli del sistema",
        "exit": "Esci",
        "main_footer": "D-pad/stick: muovi   A/Invio: seleziona",
        "back": "Indietro",
        "cancel": "Annulla",
        "download": "Scarica",
        "true": "Vero",
        "false": "Falso",
        "language": "Lingua",
        "choose_language": "SCEGLI LINGUA",
        "language_footer": "La lingua scelta viene applicata subito",
        "language_saved": "LINGUA SALVATA",
        "language_saved_message": "La lingua dell'interfaccia ora è {language}.",
        "choose_platform": "SCEGLI PIATTAFORMA",
        "back_footer": "B/Escape: indietro",
        "search_title": "CERCA {platform}",
        "search_empty_hint": "FINE senza testo: mostra tutti i giochi",
        "searching": "RICERCA",
        "looking_for": "Ricerca di {query}...",
        "loading_all": "Caricamento di tutti i giochi {platform}...",
        "no_results": "NESSUN RISULTATO",
        "nothing_matched": "Nessun risultato per {query}.",
        "catalogue_empty": "Il catalogo è vuoto.",
        "checking_compatibility": "VERIFICA COMPATIBILITÀ",
        "matching_compatibility": "Confronto con il catalogo di compatibilità locale...",
        "results_title": "RISULTATI {store} ({count})",
        "results_footer": "A/Invio: dettagli   B/Escape: indietro",
        "title_details": "DETTAGLI DEL GIOCO",
        "select_download": "Scegli Scarica per continuare",
        "system_field": "Sistema: {value}",
        "region_field": "Regione: {value}",
        "version_field": "Versione: {value}",
        "languages_field": "Lingue: {value}",
        "rating_field": "Valutazione: {value}",
        "compatibility_field": "Compatibilità: {value}",
        "compatibility_badge": "Compatibilità: {value}",
        "settings_title": "IMPOSTAZIONI",
        "settings_footer": "Impostazioni store, interfaccia, cache, log e applicazione",
        "change_store": "Cambia store  [attuale: {value}]",
        "refresh_store_cache": "Aggiorna catalogo giochi  [{count} salvati]",
        "update_bios_catalogue": "Aggiorna catalogo RetroBIOS  [{status}]",
        "update_compatibility": "Aggiorna catalogo compatibilità  [{status}]",
        "cache_lifetime": "Durata cache cataloghi  [{days} giorni]",
        "max_concurrent_downloads": "Download simultanei  [{count}]",
        "max_concurrent_downloads_title": "NUMERO MASSIMO DI DOWNLOAD SIMULTANEI",
        "max_concurrent_downloads_hint": "Valore attuale: {current}; intervallo consentito: 1-8",
        "max_concurrent_downloads_range": "Inserisci un numero intero da 1 a 8.",
        "max_concurrent_downloads_saved": "LIMITE DOWNLOAD SALVATO",
        "max_concurrent_downloads_saved_message": (
            "Dopo il riavvio verranno eseguiti fino a {count} download simultanei."
        ),
        "rate_limit_retry_settings": "Impostazioni tentativi per limite",
        "rate_limit_retry_title": "TENTATIVI PER LIMITE",
        "rate_limit_retry_footer": "Le modifiche valgono per i nuovi tentativi",
        "rate_limit_retry_base": "Ritardo iniziale  [{value:g} secondi]",
        "rate_limit_retry_max": "Ritardo massimo  [{value:g} secondi]",
        "rate_limit_retry_jitter": "Variazione casuale  [{value:g}%]",
        "rate_limit_retry_base_seconds_title": "RITARDO INIZIALE (SECONDI)",
        "rate_limit_retry_max_seconds_title": "RITARDO MASSIMO (SECONDI)",
        "rate_limit_retry_jitter_ratio_title": "VARIAZIONE CASUALE (PERCENTUALE)",
        "rate_limit_retry_invalid": (
            "Usa 1-3600 secondi iniziali, fino a 86400 secondi massimi e 0-100% di "
            "variazione. Il massimo non può essere inferiore al valore iniziale."
        ),
        "rate_limit_retry_saved": "IMPOSTAZIONI TENTATIVI SALVATE",
        "rate_limit_retry_saved_message": "I nuovi tentativi useranno questi valori.",
        "log_level": "Livello log  [{value}]",
        "file_logging": "Scrivi log su file  [{value}]",
        "minerva_settings": "Impostazioni BitTorrent Minerva",
        "check_update": "Controlla aggiornamenti  [installata: v{version}]",
        "not_set": "non impostato",
        "on": "sì",
        "off": "no",
        "cache_days_title": "GIORNI CACHE CATALOGO",
        "cache_days_hint": "Attuale: {current}; predefinito: {default}",
        "cache_lifetime_saved": "DURATA CACHE SALVATA",
        "cache_lifetime_saved_message": "I cataloghi scadono dopo {days} giorno/i.",
        "invalid_cache_lifetime": "Durata catalogo non valida: {error}",
        "log_level_title": "LIVELLO LOG",
        "log_level_footer": "Il livello scelto viene applicato subito",
        "log_level_saved": "LIVELLO LOG SALVATO",
        "log_level_saved_message": "Il livello log ora è {level}.",
        "file_logging_title": "SCRIVERE I LOG SU FILE?",
        "file_logging_footer": "La modifica è immediata e viene salvata",
        "file_logging_saved": "LOG SU FILE SALVATO",
        "file_logging_enabled": "Il log su file è attivo in:\n{path}",
        "file_logging_failed": (
            "Impossibile attivare il log su file. Controlla i permessi di scrittura."
        ),
        "file_logging_disabled": "Il log su file è disattivato.",
        "integer_keyboard": "Solo numeri",
        "float_keyboard": "Solo numeri e punto decimale",
        "mixed_keyboard": "Lettere, numeri e simboli",
        "keyboard_footer": (
            "{page}   D-pad: muovi   A: tasto   X: conferma   Y: cancella   B: annulla"
        ),
        "space": "SPAZIO",
        "done": "FINE",
        "key_back": "CANCELLA",
        "error": "ERRORE",
        "continue_footer": "A/Invio/B/Escape: continua",
        "choose_store_catalogue": "SCEGLI CATALOGO STORE",
        "choose_store_footer": "Scegli uno store; B/Escape: indietro",
        "refresh_store_title": "AGGIORNA {store}",
        "refresh_store_footer": "Sostituisce la cache selezionata prima della scadenza",
        "refreshing_catalogue": "AGGIORNAMENTO CATALOGO GIOCHI",
        "refreshing_catalogue_message": "Download del catalogo completo {store} per {platform}...",
        "catalogue_updated": "CATALOGO GIOCHI AGGIORNATO",
        "catalogue_updated_message": "Salvati {count} risultati {store} per {platform}.",
        "not_downloaded": "non scaricato",
        "fresh_games": "aggiornato, {count} giochi",
        "stale_games": "scaduto, {count} giochi",
        "compatibility_update_title": "AGGIORNARE IL CATALOGO COMPATIBILITÀ?",
        "compatibility_update_download": "Scarica il catalogo compatibilità più recente",
        "keep_catalogue": "Mantieni il catalogo attuale",
        "keep_cache_footer": "La cache esistente resta disponibile in caso di errore",
        "compatibility_updating": "AGGIORNAMENTO COMPATIBILITÀ",
        "compatibility_updating_message": "Download del catalogo compatibilità corrente...",
        "compatibility_updated": "CATALOGO COMPATIBILITÀ AGGIORNATO",
        "compatibility_updated_message": "Salvati {count} titoli. Valido per {days} giorno/i.",
        "automatic_update_package": (
            "Gli aggiornamenti automatici sono disponibili nel pacchetto autonomo per "
            "il sistema operativo scelto. Gli ambienti locali si aggiornano con git e uv."
        ),
    },
    "pt": {
        "app_title": "POCKET HARBOR",
        "search_library": "Pesquisar na biblioteca",
        "direct_download": "Transferir a partir de uma ligação",
        "download_queue": "Transferências",
        "manage_games": "Gerir jogos instalados",
        "search_bios": "Pesquisar e transferir BIOS",
        "settings": "Definições",
        "status_controls": "Estado e controlos do sistema",
        "exit": "Sair",
        "main_footer": "Direcional/analógico: mover   A/Enter: selecionar",
        "back": "Voltar",
        "cancel": "Cancelar",
        "download": "Transferir",
        "true": "Verdadeiro",
        "false": "Falso",
        "language": "Idioma",
        "choose_language": "ESCOLHER IDIOMA",
        "language_footer": "O idioma escolhido é aplicado imediatamente",
        "language_saved": "IDIOMA GUARDADO",
        "language_saved_message": "O idioma da interface agora é {language}.",
        "choose_platform": "ESCOLHER PLATAFORMA",
        "back_footer": "B/Escape: voltar",
        "search_title": "PESQUISAR {platform}",
        "search_empty_hint": "CONCLUIR sem texto: mostrar todos os jogos",
        "searching": "A PESQUISAR",
        "looking_for": "A pesquisar {query}...",
        "loading_all": "A carregar todos os jogos de {platform}...",
        "no_results": "SEM RESULTADOS",
        "nothing_matched": "Nenhum resultado para {query}.",
        "catalogue_empty": "O catálogo está vazio.",
        "checking_compatibility": "A VERIFICAR COMPATIBILIDADE",
        "matching_compatibility": "A comparar com o catálogo de compatibilidade local...",
        "results_title": "RESULTADOS {store} ({count})",
        "results_footer": "A/Enter: detalhes   B/Escape: voltar",
        "title_details": "DETALHES DO JOGO",
        "select_download": "Escolha Transferir para continuar",
        "system_field": "Sistema: {value}",
        "region_field": "Região: {value}",
        "version_field": "Versão: {value}",
        "languages_field": "Idiomas: {value}",
        "rating_field": "Classificação: {value}",
        "compatibility_field": "Compatibilidade: {value}",
        "compatibility_badge": "Compatibilidade: {value}",
        "settings_title": "DEFINIÇÕES",
        "settings_footer": "Definições de loja, interface, cache, registo e aplicação",
        "change_store": "Alterar loja  [atual: {value}]",
        "refresh_store_cache": "Atualizar catálogo de jogos  [{count} guardados]",
        "update_bios_catalogue": "Atualizar catálogo RetroBIOS  [{status}]",
        "update_compatibility": "Atualizar catálogo de compatibilidade  [{status}]",
        "cache_lifetime": "Duração da cache  [{days} dias]",
        "max_concurrent_downloads": "Transferências simultâneas  [{count}]",
        "max_concurrent_downloads_title": "MÁXIMO DE TRANSFERÊNCIAS SIMULTÂNEAS",
        "max_concurrent_downloads_hint": "Valor atual: {current}; intervalo permitido: 1-8",
        "max_concurrent_downloads_range": "Introduza um número inteiro de 1 a 8.",
        "max_concurrent_downloads_saved": "LIMITE DE TRANSFERÊNCIAS GUARDADO",
        "max_concurrent_downloads_saved_message": (
            "Após reiniciar, serão executadas até {count} transferências simultâneas."
        ),
        "rate_limit_retry_settings": "Definições de repetição por limite",
        "rate_limit_retry_title": "REPETIÇÕES POR LIMITE",
        "rate_limit_retry_footer": "As alterações aplicam-se a novas tentativas",
        "rate_limit_retry_base": "Espera inicial  [{value:g} segundos]",
        "rate_limit_retry_max": "Espera máxima  [{value:g} segundos]",
        "rate_limit_retry_jitter": "Variação aleatória  [{value:g}%]",
        "rate_limit_retry_base_seconds_title": "ESPERA INICIAL (SEGUNDOS)",
        "rate_limit_retry_max_seconds_title": "ESPERA MÁXIMA (SEGUNDOS)",
        "rate_limit_retry_jitter_ratio_title": "VARIAÇÃO ALEATÓRIA (PERCENTAGEM)",
        "rate_limit_retry_invalid": (
            "Use 1-3600 segundos inicialmente, até 86400 segundos no máximo e 0-100% de "
            "variação. O máximo não pode ser inferior ao valor inicial."
        ),
        "rate_limit_retry_saved": "DEFINIÇÕES DE REPETIÇÃO GUARDADAS",
        "rate_limit_retry_saved_message": "As novas tentativas usarão estes valores.",
        "log_level": "Nível de registo  [{value}]",
        "file_logging": "Guardar registo em ficheiro  [{value}]",
        "minerva_settings": "Definições BitTorrent do Minerva",
        "check_update": "Procurar atualização  [instalada: v{version}]",
        "not_set": "não definido",
        "on": "sim",
        "off": "não",
        "cache_days_title": "DIAS DE CACHE DO CATÁLOGO",
        "cache_days_hint": "Atual: {current}; predefinido: {default}",
        "cache_lifetime_saved": "DURAÇÃO GUARDADA",
        "cache_lifetime_saved_message": "Os catálogos expiram após {days} dia(s).",
        "invalid_cache_lifetime": "Duração inválida: {error}",
        "log_level_title": "NÍVEL DE REGISTO",
        "log_level_footer": "O nível escolhido é aplicado imediatamente",
        "log_level_saved": "NÍVEL GUARDADO",
        "log_level_saved_message": "O nível de registo agora é {level}.",
        "file_logging_title": "GUARDAR REGISTO EM FICHEIRO?",
        "file_logging_footer": "A alteração é imediata e fica guardada",
        "file_logging_saved": "REGISTO GUARDADO",
        "file_logging_enabled": "O registo está ativo em:\n{path}",
        "file_logging_failed": (
            "Não foi possível ativar o registo. Verifique as permissões de escrita."
        ),
        "file_logging_disabled": "O registo em ficheiro está desativado.",
        "integer_keyboard": "Apenas números",
        "float_keyboard": "Apenas números e ponto decimal",
        "mixed_keyboard": "Letras, números e símbolos",
        "keyboard_footer": (
            "{page}   Direcional: mover   A: tecla   X: confirmar   Y: apagar   B: cancelar"
        ),
        "space": "ESPAÇO",
        "done": "CONCLUIR",
        "key_back": "APAGAR",
        "error": "ERRO",
        "continue_footer": "A/Enter/B/Escape: continuar",
        "choose_store_catalogue": "ESCOLHER CATÁLOGO DA LOJA",
        "choose_store_footer": "Escolha uma loja; B/Escape: voltar",
        "refresh_store_title": "ATUALIZAR {store}",
        "refresh_store_footer": "Substitui a cache selecionada antes de expirar",
        "refreshing_catalogue": "A ATUALIZAR CATÁLOGO DE JOGOS",
        "refreshing_catalogue_message": (
            "A transferir o catálogo completo de {store} para {platform}..."
        ),
        "catalogue_updated": "CATÁLOGO DE JOGOS ATUALIZADO",
        "catalogue_updated_message": "Guardados {count} resultados de {store} para {platform}.",
        "not_downloaded": "não transferido",
        "fresh_games": "atual, {count} jogos",
        "stale_games": "expirado, {count} jogos",
        "compatibility_update_title": "ATUALIZAR CATÁLOGO DE COMPATIBILIDADE?",
        "compatibility_update_download": "Transferir o catálogo de compatibilidade mais recente",
        "keep_catalogue": "Manter o catálogo atual",
        "keep_cache_footer": "A cache existente é mantida se a atualização falhar",
        "compatibility_updating": "A ATUALIZAR COMPATIBILIDADE",
        "compatibility_updating_message": "A transferir o catálogo de compatibilidade atual...",
        "compatibility_updated": "CATÁLOGO DE COMPATIBILIDADE ATUALIZADO",
        "compatibility_updated_message": "Guardados {count} títulos. Válido por {days} dia(s).",
        "automatic_update_package": (
            "As atualizações automáticas estão disponíveis no pacote autónomo para "
            "o sistema operativo escolhido. Os ambientes locais são atualizados com git e uv."
        ),
    },
}

_TUI_FLOW_TRANSLATIONS: dict[LanguageCode, dict[str, str]] = {
    "en": {
        "invalid_cache_lifetime": "Enter a valid catalogue cache lifetime.",
        "cache_lifetime_range": "Enter a value from 1 to 3650 days.",
        "no_download_stores": "No download stores are enabled. Check PH_STORES.",
        "loading_catalogue": "LOADING CATALOGUE",
        "loading_catalogue_progress": (
            "Reading numeric and A-Z sections...\n{current}/{total}  ({percent}%)"
        ),
        "store_description_vimm": "Vimm game vault",
        "store_description_minerva": "RetroAchievements torrents (native Python)",
        "compatibility_level_not_listed": "Not listed",
        "compatibility_level_perfect": "Perfect",
        "compatibility_level_playable": "Playable",
        "compatibility_level_limited": "Limited",
        "compatibility_level_unsupported": "Unsupported",
        "compatibility_not_listed_source": "Not listed by r36sgamelist.com",
        "compatibility_title_match": "title match {score}%",
        "compatibility_title_listed": "title listed",
        "compatibility_platform_rating": "platform rating",
        "compatibility_detail": "{level} ({qualifier})",
        "compatibility_match": "{level} - {score}% match",
        "compatibility_listed": "{level} - listed",
        "destination_platform": "DESTINATION PLATFORM",
        "destination_platform_footer": "The completed file is moved into this ROM folder",
        "download_queued": "DOWNLOAD QUEUED",
        "download_queued_message": (
            "{title}\nDownloading from {store} in the background. "
            "Open Downloads to monitor or control it."
        ),
        "download_queue_empty": "NO DOWNLOADS",
        "download_queue_empty_message": "There are no active or recently completed downloads.",
        "download_queue_title": "DOWNLOADS",
        "download_queue_footer": "Select a download to pause, resume, retry, or cancel",
        "refresh_download_status": "Refresh download status",
        "download_state_queued": "Queued",
        "download_state_downloading": "Downloading",
        "download_state_rate_limited": "Waiting to retry",
        "download_state_paused": "Paused",
        "download_state_failed": "Failed",
        "download_state_cancelled": "Cancelled",
        "download_state_completed": "Completed",
        "download_progress_percent": "{percent}%",
        "download_progress_size": "{size}",
        "download_progress_waiting": "waiting",
        "download_job_row": "{title}  [{state} - {progress}]  {store}",
        "download_store_field": "Store: {value}",
        "download_status_field": "Status: {value}",
        "download_progress_field": "Progress: {value}",
        "download_error_field": "Error: {value}",
        "download_retry_field": "Automatic retry {attempt} in about {seconds}s",
        "pause_download": "Pause download",
        "resume_download": "Resume download",
        "retry_download": "Retry download",
        "download_details_title": "DOWNLOAD DETAILS",
        "download_controls_footer": "Background downloads keep their original store",
        "download_progress_bytes": "{current} of {total}",
        "confirm_download_cancel": "CANCEL DOWNLOAD?",
        "keep_downloading": "No - keep downloading {title}",
        "cancel_and_remove_partial": "Yes - cancel and remove partial data",
        "cancel_download_warning": "Cancelled partial data cannot be resumed",
        "detail_url": "DETAIL URL",
        "platform_has_no_rom_folder": (
            "This platform has no ROM folder on the selected operating system."
        ),
        "no_rom_partition_environment": (
            "No ROM partition found. Set PH_ROMS_DIR or PH_ROMS_DIRS."
        ),
        "preparing": "PREPARING",
        "retrieving_download_link": "Retrieving the download link...",
        "download_cancelled": "DOWNLOAD CANCELLED",
        "no_game_installed": "No game was installed.",
        "installed_bundled_bios": "Installed {count} bundled BIOS file(s).",
        "installed_required_bios": ("Installed {count} required BIOS file(s) from RetroBIOS."),
        "download_complete": "DOWNLOAD COMPLETE",
        "download_complete_message": (
            "{filename}\nMoved to {destination}{bios}\n"
            "The game list will refresh when you exit Pocket Harbor."
        ),
        "no_rom_partitions": "No ROM partitions were found.",
        "choose_memory_card": "CHOOSE MEMORY CARD",
        "checking_folders": "CHECKING FOLDERS",
        "finding_installed_platforms": "Finding installed platforms on {root}...",
        "no_games_on_card": "NO GAMES ON CARD",
        "no_supported_games_on_card": "No supported game files were found on {root}.",
        "choose_installed_platform": "CHOOSE INSTALLED PLATFORM",
        "installed_platform_footer": ("Platforms are detected quickly; games load after selection"),
        "scanning_platform": "SCANNING PLATFORM",
        "reading_platform": "Reading only {platform} on {root}...",
        "no_games": "NO GAMES",
        "no_platform_games": "No {platform} games were found.",
        "platform_on_card": "{platform} ON {root}",
        "manage_games_footer": "A: manage   B: back   L1/R1: page",
        "refreshing": "REFRESHING",
        "refreshing_platform": "Refreshing {platform} only...",
        "card_field": "Card: {value}",
        "file_field": "File: {value}",
        "files_in_group": "Files in group: {count}",
        "update_from_remote": "Update from remote",
        "delete_from_device": "Delete from device",
        "manage_game": "MANAGE GAME",
        "manage_game_footer": "Updates keep the same card and platform",
        "confirm_permanent_delete": "CONFIRM PERMANENT DELETE",
        "keep_game": "No - keep {title}",
        "delete_files": "Yes - delete {count} file(s)",
        "delete_warning": "Deleted files cannot be recovered",
        "game_deleted": "GAME DELETED",
        "game_deleted_message": (
            "{title}\nThe game list will refresh when you exit Pocket Harbor."
        ),
        "store_platform_unsupported": (
            "{store} does not support {platform}. Choose another store in Settings."
        ),
        "searching_for_update": "SEARCHING FOR UPDATE",
        "no_remote_match": "NO REMOTE MATCH",
        "choose_replacement": "CHOOSE REPLACEMENT",
        "replacement_footer": "The old game is removed only after download completes",
        "confirm_update": "CONFIRM UPDATE",
        "keep_file": "Cancel - keep {filename}",
        "replace_with": "Replace with {title}",
        "confirm_choice_footer": "A/Enter: confirm choice",
        "update_cancelled": "UPDATE CANCELLED",
        "update_queued": "UPDATE QUEUED",
        "update_queued_message": (
            "{title}\nThe replacement from {store} is downloading in the background. "
            "The installed game stays unchanged until it completes."
        ),
        "installed_game_unchanged": "The installed game was not changed.",
        "game_updated": "GAME UPDATED",
        "game_updated_message": (
            "{filename}\nInstalled on {destination}{bundled}{required}\n"
            "The game list will refresh when you exit Pocket Harbor."
        ),
        "choose_destination_card": "CHOOSE DESTINATION CARD",
        "choose_store_footer": "Choose a download store; B/Escape returns",
        "first_run_store": "FIRST-RUN DOWNLOAD STORE",
        "choose_default_store": "CHOOSE DEFAULT STORE",
        "settings_saved": "SETTINGS SAVED",
        "store_saved_message": "Searches, downloads, and updates will use {store}.",
        "store_cached_count": "{store}  [{count} cached]",
        "cache_invalid": "cache invalid",
        "stale_over_days": "stale (>{days} days)",
        "fresh": "fresh",
        "connecting_retrobios": "Connecting to RetroBIOS...",
        "finding_retrobios_revision": "Finding the latest RetroBIOS revision",
        "downloading_retrobios_profiles": "Downloading RetroBIOS core profiles",
        "retrobios_update_title": "UPDATE RETROBIOS CATALOGUE?",
        "download_latest_metadata": "Download latest metadata",
        "catalogue_unchanged": "The existing catalogue was not changed.",
        "retrobios_update_cancelled": "RETROBIOS UPDATE CANCELLED",
        "retrobios_updated": "RETROBIOS UPDATED",
        "retrobios_summary": (
            "Revision: {revision}\nSystems: {systems}\nRetroArch profile: {profile}"
        ),
        "unknown": "unknown",
        "choose_bios_memory_card": "CHOOSE BIOS MEMORY CARD",
        "no_rom_partition": "No ROM partition was found.",
        "search_bios_title": "SEARCH BIOS",
        "search_bios_empty_hint": "DONE with no text: list the full BIOS catalogue",
        "no_bios_results": "NO BIOS RESULTS",
        "bios_catalogue_empty": "The BIOS catalogue is empty.",
        "bios_results": "BIOS RESULTS ({count})",
        "bios_results_footer": "Select a BIOS to inspect or download; B/Escape returns",
        "bios_details": "BIOS DETAILS",
        "platform_field": "Platform: {value}",
        "status_field": "Status: {value}",
        "required": "Required",
        "optional": "Optional",
        "required_short": "R",
        "optional_short": "O",
        "all_regions": "all",
        "destination_field": "Destination: {value}",
        "bios_state_valid": "valid",
        "bios_state_missing": "missing",
        "bios_state_invalid": "invalid",
        "bios_entry_not_downloadable": (
            "RetroBIOS has metadata but no downloadable file for this entry."
        ),
        "bios_check_unavailable": "BIOS CHECK UNAVAILABLE",
        "bios_check_unavailable_message": (
            "The game was installed, but RetroBIOS metadata could not be loaded:\n{error}\n"
            "You can retry from Search and download BIOS."
        ),
        "required_bios_not_found": "REQUIRED BIOS NOT FOUND",
        "required_bios_missing_message": (
            "The game archive did not provide these required BIOS files, and no valid "
            "copy was found on either memory card:"
        ),
        "and_more": "...and {count} more",
        "download_required_bios": "DOWNLOAD REQUIRED BIOS?",
        "download_from_retrobios": "Download from RetroBIOS",
        "keep_without_bios": "Keep the game without BIOS",
        "firmware_warning": "The game may not start without required firmware",
        "bios_not_downloadable": "BIOS NOT DOWNLOADABLE",
        "bios_not_downloadable_message": (
            "RetroBIOS has requirement metadata but no downloadable copy for the selected files."
        ),
        "confirm_retrobios_download": "CONFIRM RETROBIOS DOWNLOAD",
        "download_verified_bios": "Download {count} verified BIOS file(s)",
        "bios_legal_footer": (
            "Only continue if you are permitted to obtain these personal backup files"
        ),
        "bios_download_cancelled": "BIOS DOWNLOAD CANCELLED",
        "no_incomplete_bios_installed": "No incomplete BIOS file was installed.",
        "bios_installed": "BIOS INSTALLED",
        "bios_installed_message": ("Installed and verified {count} BIOS file(s) in {destination}."),
        "minerva_settings_title": "MINERVA BITTORRENT SETTINGS",
        "minerva_udp_protocol_id": "UDP protocol ID",
        "minerva_block_size": "Block size (bytes)",
        "minerva_max_torrent_bytes": "Max torrent metadata (bytes)",
        "minerva_max_tracker_bytes": "Max tracker response (bytes)",
        "minerva_max_peer_attempts": "Max peer attempts",
        "minerva_peer_race_workers": "Peer race workers",
        "minerva_max_peer_timeout": "Max peer timeout (seconds)",
        "minerva_max_tracker_queries": "Max tracker queries",
        "minerva_max_discovered_peers": "Max discovered peers",
        "reset_all_defaults": "Reset all to defaults",
        "minerva_settings_footer": "Advanced values are saved locally",
        "reset_minerva_settings": "RESET MINERVA SETTINGS?",
        "keep_current_values": "No - keep current values",
        "restore_defaults": "Yes - restore defaults",
        "reset_minerva_footer": "This changes all nine BitTorrent values",
        "current_value": "Current: {value}",
        "invalid_setting": "Invalid {setting}: {error}",
        "minerva_settings_saved": "MINERVA SETTINGS SAVED",
        "minerva_settings_saved_message": (
            "The new values will be used by the next Minerva download."
        ),
        "checking_for_update": "CHECKING FOR UPDATE",
        "checking_for_update_message": (
            "Installed: v{version}\nReading the latest GitHub release..."
        ),
        "already_up_to_date": "ALREADY UP TO DATE",
        "latest_release_message": ("v{version} is the latest published {target} release."),
        "application_update_available": "APPLICATION UPDATE AVAILABLE",
        "download_install_version": "Download and install v{version}",
        "later": "Later",
        "installed_published": "Installed: v{installed}   Published: {published}",
        "installed_application_unchanged": "The installed application was not changed.",
        "update_ready": "UPDATE READY",
        "update_ready_message": (
            "v{version} will be installed now.\n"
            "Reopen Pocket Harbor from Tools after this screen closes."
        ),
        "connecting_github": "Connecting to GitHub...",
        "cancelling_update": "CANCELLING UPDATE",
        "cancelling_update_message": (
            "Removing the incomplete update; the installed version is unchanged..."
        ),
        "exit_pocket_harbor": "EXIT POCKET HARBOR?",
        "return_to_pocket_harbor": "No - return to Pocket Harbor",
        "confirm_exit": "Yes - exit",
        "exit_footer": "Confirm before returning to EmulationStation",
        "card_number": "CARD {index}",
        "choose_library_location": "Choose where the game library is stored",
        "downloading": "DOWNLOADING",
        "downloaded_kib": "{label}\n{kib} KiB downloaded",
        "cancel_download_footer": "B/Escape: cancel download",
        "connecting_download_service": "Connecting to the download service...",
        "cancelling_download": "CANCELLING DOWNLOAD",
        "cancelling_download_message": (
            "Closing active network connections and removing partial files..."
        ),
        "minerva_torrent_changed": "MINERVA TORRENT CHANGED",
        "minerva_torrent_changed_message": (
            "Catalogue file:\n{filename}\nCatalogue position: #{index}\n\n"
            "The torrent now contains {count} files and no longer has one unambiguous "
            "match. Review the closest candidates or cancel; no game has been installed yet."
        ),
        "minerva_candidate": "#{index}  {filename}  | {size} | {score}% title match | {path}",
        "choose_minerva_torrent_file": "CHOOSE MINERVA TORRENT FILE",
        "minerva_candidates_footer": ("These are the closest safe candidates; B/Escape cancels"),
        "review_minerva_file": "REVIEW MINERVA FILE",
        "review_minerva_file_message": (
            "Catalogue expected:\n{expected}\n\nSelected torrent file:\n{selected}\n"
            "Torrent position: #{index}\nSize: {size}\nTitle similarity: {score}%"
        ),
        "confirm_minerva_file": "CONFIRM MINERVA FILE",
        "cancel_download": "Cancel download",
        "download_filename": "Download {filename}",
        "confirm_minerva_file_footer": (
            "Only the explicitly selected torrent file will be downloaded"
        ),
        "not_detected": "not detected",
        "not_configured": "not configured",
        "status_title": "POCKET HARBOR STATUS",
        "status_message": (
            "Default store: {store}\nStores: {stores}\nStaging: {staging}\nROM root: {roms}\n"
            "Platforms: {platforms}\nHardware: {hardware}\nCompatible: {compatible}\n"
            "Display: {resolution} pixels; {width}x{height} terminal cells\n"
            "DT inputs: {inputs} ({keys} GPIO keys)\n"
            "Controller: {controller} (native Linux input)\n\nControls\n"
            "D-pad / sticks / arrows   Move selection\nA / Enter        Select\n"
            "B / Escape       Go back\nX                Submit search text\n\n"
            "Search text can be entered with the built-in on-screen keyboard."
        ),
        "keyboard_letters": "LETTERS",
        "keyboard_symbols": "SYMBOLS",
        "keyboard_accents": "ACCENTS",
        "operation_failed": "The operation failed.\nTechnical details: {error}",
        "terminal_too_small": "Terminal must be at least 40 columns by 15 rows.",
    },
    "de": {
        "invalid_cache_lifetime": "Geben Sie eine gültige Katalog-Cache-Dauer ein.",
        "cache_lifetime_range": "Geben Sie einen Wert zwischen 1 und 3650 Tagen ein.",
        "no_download_stores": "Keine Download-Stores sind aktiviert. Prüfen Sie PH_STORES.",
        "loading_catalogue": "KATALOG WIRD GELADEN",
        "loading_catalogue_progress": (
            "Zahlen- und A-Z-Bereiche werden gelesen...\n{current}/{total}  ({percent} %)"
        ),
        "store_description_vimm": "Vimm-Spielearchiv",
        "store_description_minerva": "RetroAchievements-Torrents (natives Python)",
        "compatibility_level_not_listed": "Nicht gelistet",
        "compatibility_level_perfect": "Perfekt",
        "compatibility_level_playable": "Spielbar",
        "compatibility_level_limited": "Eingeschränkt",
        "compatibility_level_unsupported": "Nicht unterstützt",
        "compatibility_not_listed_source": "Nicht auf r36sgamelist.com gelistet",
        "compatibility_title_match": "Titelübereinstimmung {score} %",
        "compatibility_title_listed": "Titel gelistet",
        "compatibility_platform_rating": "Plattformbewertung",
        "compatibility_detail": "{level} ({qualifier})",
        "compatibility_match": "{level} - {score} % Übereinstimmung",
        "compatibility_listed": "{level} - gelistet",
        "destination_platform": "ZIELPLATTFORM",
        "destination_platform_footer": "Die fertige Datei wird in diesen ROM-Ordner verschoben",
        "download_queued": "DOWNLOAD EINGEREIHT",
        "download_queued_message": (
            "{title}\nWird im Hintergrund von {store} heruntergeladen. "
            "Unter Downloads können Sie den Vorgang überwachen oder steuern."
        ),
        "download_queue_empty": "KEINE DOWNLOADS",
        "download_queue_empty_message": "Keine aktiven oder kürzlich abgeschlossenen Downloads.",
        "download_queue_title": "DOWNLOADS",
        "download_queue_footer": (
            "Download zum Pausieren, Fortsetzen, Wiederholen oder Abbrechen wählen"
        ),
        "refresh_download_status": "Downloadstatus aktualisieren",
        "download_state_queued": "Eingereiht",
        "download_state_downloading": "Wird geladen",
        "download_state_rate_limited": "Wartet auf erneuten Versuch",
        "download_state_paused": "Pausiert",
        "download_state_failed": "Fehlgeschlagen",
        "download_state_cancelled": "Abgebrochen",
        "download_state_completed": "Abgeschlossen",
        "download_progress_percent": "{percent}%",
        "download_progress_size": "{size}",
        "download_progress_waiting": "wartet",
        "download_job_row": "{title}  [{state} - {progress}]  {store}",
        "download_store_field": "Store: {value}",
        "download_status_field": "Status: {value}",
        "download_progress_field": "Fortschritt: {value}",
        "download_error_field": "Fehler: {value}",
        "download_retry_field": "Automatischer Versuch {attempt} in etwa {seconds}s",
        "pause_download": "Download pausieren",
        "resume_download": "Download fortsetzen",
        "retry_download": "Download wiederholen",
        "download_details_title": "DOWNLOAD-DETAILS",
        "download_controls_footer": "Hintergrund-Downloads behalten ihren ursprünglichen Store",
        "download_progress_bytes": "{current} von {total}",
        "confirm_download_cancel": "DOWNLOAD ABBRECHEN?",
        "keep_downloading": "Nein - {title} weiter herunterladen",
        "cancel_and_remove_partial": "Ja - abbrechen und Teildaten löschen",
        "cancel_download_warning": "Gelöschte Teildaten können nicht fortgesetzt werden",
        "detail_url": "DETAIL-URL",
        "platform_has_no_rom_folder": (
            "Diese Plattform hat auf dem gewählten Betriebssystem keinen ROM-Ordner."
        ),
        "no_rom_partition_environment": (
            "Keine ROM-Partition gefunden. Setzen Sie PH_ROMS_DIR oder PH_ROMS_DIRS."
        ),
        "preparing": "VORBEREITUNG",
        "retrieving_download_link": "Download-Link wird abgerufen...",
        "download_cancelled": "DOWNLOAD ABGEBROCHEN",
        "no_game_installed": "Es wurde kein Spiel installiert.",
        "installed_bundled_bios": "{count} enthaltene BIOS-Datei(en) installiert.",
        "installed_required_bios": (
            "{count} erforderliche BIOS-Datei(en) aus RetroBIOS installiert."
        ),
        "download_complete": "DOWNLOAD ABGESCHLOSSEN",
        "download_complete_message": (
            "{filename}\nNach {destination} verschoben{bios}\n"
            "Die Spieleliste wird beim Beenden von Pocket Harbor aktualisiert."
        ),
        "no_rom_partitions": "Keine ROM-Partitionen gefunden.",
        "choose_memory_card": "SPEICHERKARTE AUSWÄHLEN",
        "checking_folders": "ORDNER WERDEN GEPRÜFT",
        "finding_installed_platforms": "Installierte Plattformen auf {root} werden gesucht...",
        "no_games_on_card": "KEINE SPIELE AUF DER KARTE",
        "no_supported_games_on_card": "Auf {root} wurden keine unterstützten Spiele gefunden.",
        "choose_installed_platform": "INSTALLIERTE PLATTFORM AUSWÄHLEN",
        "installed_platform_footer": (
            "Plattformen werden schnell erkannt; Spiele laden nach der Auswahl"
        ),
        "scanning_platform": "PLATTFORM WIRD DURCHSUCHT",
        "reading_platform": "Nur {platform} auf {root} wird gelesen...",
        "no_games": "KEINE SPIELE",
        "no_platform_games": "Keine Spiele für {platform} gefunden.",
        "platform_on_card": "{platform} AUF {root}",
        "manage_games_footer": "A: verwalten   B: zurück   L1/R1: Seite",
        "refreshing": "AKTUALISIERUNG",
        "refreshing_platform": "Nur {platform} wird aktualisiert...",
        "card_field": "Karte: {value}",
        "file_field": "Datei: {value}",
        "files_in_group": "Dateien in der Gruppe: {count}",
        "update_from_remote": "Vom Store aktualisieren",
        "delete_from_device": "Vom Gerät löschen",
        "manage_game": "SPIEL VERWALTEN",
        "manage_game_footer": "Updates behalten Karte und Plattform bei",
        "confirm_permanent_delete": "ENDGÜLTIGES LÖSCHEN BESTÄTIGEN",
        "keep_game": "Nein - {title} behalten",
        "delete_files": "Ja - {count} Datei(en) löschen",
        "delete_warning": "Gelöschte Dateien können nicht wiederhergestellt werden",
        "game_deleted": "SPIEL GELÖSCHT",
        "game_deleted_message": (
            "{title}\nDie Spieleliste wird beim Beenden von Pocket Harbor aktualisiert."
        ),
        "store_platform_unsupported": (
            "{store} unterstützt {platform} nicht. Wählen Sie in den Einstellungen einen "
            "anderen Store."
        ),
        "searching_for_update": "UPDATE WIRD GESUCHT",
        "no_remote_match": "KEIN TREFFER IM STORE",
        "choose_replacement": "ERSATZ AUSWÄHLEN",
        "replacement_footer": "Das alte Spiel wird erst nach dem Download entfernt",
        "confirm_update": "UPDATE BESTÄTIGEN",
        "keep_file": "Abbrechen - {filename} behalten",
        "replace_with": "Durch {title} ersetzen",
        "confirm_choice_footer": "A/Enter: Auswahl bestätigen",
        "update_cancelled": "UPDATE ABGEBROCHEN",
        "update_queued": "UPDATE EINGEREIHT",
        "update_queued_message": (
            "{title}\nDer Ersatz von {store} wird im Hintergrund geladen. "
            "Das installierte Spiel bleibt bis zum Abschluss unverändert."
        ),
        "installed_game_unchanged": "Das installierte Spiel wurde nicht geändert.",
        "game_updated": "SPIEL AKTUALISIERT",
        "game_updated_message": (
            "{filename}\nInstalliert auf {destination}{bundled}{required}\n"
            "Die Spieleliste wird beim Beenden von Pocket Harbor aktualisiert."
        ),
        "choose_destination_card": "ZIELKARTE AUSWÄHLEN",
        "choose_store_footer": "Download-Store auswählen; B/Escape: zurück",
        "first_run_store": "DOWNLOAD-STORE FÜR DEN ERSTEN START",
        "choose_default_store": "STANDARD-STORE AUSWÄHLEN",
        "settings_saved": "EINSTELLUNGEN GESPEICHERT",
        "store_saved_message": "Suche, Downloads und Updates verwenden jetzt {store}.",
        "store_cached_count": "{store}  [{count} gespeichert]",
        "cache_invalid": "Cache ungültig",
        "stale_over_days": "veraltet (>{days} Tage)",
        "fresh": "aktuell",
        "connecting_retrobios": "Verbindung zu RetroBIOS wird hergestellt...",
        "finding_retrobios_revision": "Neueste RetroBIOS-Version wird gesucht",
        "downloading_retrobios_profiles": "RetroBIOS-Core-Profile werden geladen",
        "retrobios_update_title": "RETROBIOS-KATALOG AKTUALISIEREN?",
        "download_latest_metadata": "Neueste Metadaten herunterladen",
        "catalogue_unchanged": "Der vorhandene Katalog wurde nicht geändert.",
        "retrobios_update_cancelled": "RETROBIOS-UPDATE ABGEBROCHEN",
        "retrobios_updated": "RETROBIOS AKTUALISIERT",
        "retrobios_summary": (
            "Version: {revision}\nSysteme: {systems}\nRetroArch-Profil: {profile}"
        ),
        "unknown": "unbekannt",
        "choose_bios_memory_card": "BIOS-SPEICHERKARTE AUSWÄHLEN",
        "no_rom_partition": "Keine ROM-Partition gefunden.",
        "search_bios_title": "BIOS SUCHEN",
        "search_bios_empty_hint": "FERTIG ohne Text: vollständigen BIOS-Katalog anzeigen",
        "no_bios_results": "KEINE BIOS-ERGEBNISSE",
        "bios_catalogue_empty": "Der BIOS-Katalog ist leer.",
        "bios_results": "BIOS-ERGEBNISSE ({count})",
        "bios_results_footer": "BIOS prüfen oder laden; B/Escape: zurück",
        "bios_details": "BIOS-DETAILS",
        "platform_field": "Plattform: {value}",
        "status_field": "Status: {value}",
        "required": "Erforderlich",
        "optional": "Optional",
        "required_short": "E",
        "optional_short": "O",
        "all_regions": "alle",
        "destination_field": "Ziel: {value}",
        "bios_state_valid": "gültig",
        "bios_state_missing": "fehlt",
        "bios_state_invalid": "ungültig",
        "bios_entry_not_downloadable": (
            "RetroBIOS enthält Metadaten, aber keine herunterladbare Datei für diesen Eintrag."
        ),
        "bios_check_unavailable": "BIOS-PRÜFUNG NICHT VERFÜGBAR",
        "bios_check_unavailable_message": (
            "Das Spiel wurde installiert, aber RetroBIOS-Metadaten konnten nicht geladen "
            "werden:\n{error}\nSie können es über die BIOS-Suche erneut versuchen."
        ),
        "required_bios_not_found": "ERFORDERLICHES BIOS NICHT GEFUNDEN",
        "required_bios_missing_message": (
            "Das Spielarchiv enthielt diese erforderlichen BIOS-Dateien nicht, und auf "
            "keiner Speicherkarte wurde eine gültige Kopie gefunden:"
        ),
        "and_more": "...und {count} weitere",
        "download_required_bios": "ERFORDERLICHES BIOS HERUNTERLADEN?",
        "download_from_retrobios": "Von RetroBIOS herunterladen",
        "keep_without_bios": "Spiel ohne BIOS behalten",
        "firmware_warning": (
            "Ohne die erforderliche Firmware startet das Spiel möglicherweise nicht"
        ),
        "bios_not_downloadable": "BIOS NICHT HERUNTERLADBAR",
        "bios_not_downloadable_message": (
            "RetroBIOS enthält Anforderungsdaten, aber keine herunterladbare Kopie der "
            "ausgewählten Dateien."
        ),
        "confirm_retrobios_download": "RETROBIOS-DOWNLOAD BESTÄTIGEN",
        "download_verified_bios": "{count} geprüfte BIOS-Datei(en) herunterladen",
        "bios_legal_footer": (
            "Nur fortfahren, wenn Sie diese persönlichen Sicherungen beziehen dürfen"
        ),
        "bios_download_cancelled": "BIOS-DOWNLOAD ABGEBROCHEN",
        "no_incomplete_bios_installed": "Es wurde keine unvollständige BIOS-Datei installiert.",
        "bios_installed": "BIOS INSTALLIERT",
        "bios_installed_message": (
            "{count} BIOS-Datei(en) geprüft und in {destination} installiert."
        ),
        "minerva_settings_title": "MINERVA-BITTORRENT-EINSTELLUNGEN",
        "minerva_udp_protocol_id": "UDP-Protokoll-ID",
        "minerva_block_size": "Blockgröße (Byte)",
        "minerva_max_torrent_bytes": "Max. Torrent-Metadaten (Byte)",
        "minerva_max_tracker_bytes": "Max. Tracker-Antwort (Byte)",
        "minerva_max_peer_attempts": "Max. Peer-Versuche",
        "minerva_peer_race_workers": "Parallele Peer-Suchen",
        "minerva_max_peer_timeout": "Max. Peer-Zeitlimit (Sekunden)",
        "minerva_max_tracker_queries": "Max. Tracker-Anfragen",
        "minerva_max_discovered_peers": "Max. gefundene Peers",
        "reset_all_defaults": "Alle Standardwerte wiederherstellen",
        "minerva_settings_footer": "Erweiterte Werte werden lokal gespeichert",
        "reset_minerva_settings": "MINERVA-EINSTELLUNGEN ZURÜCKSETZEN?",
        "keep_current_values": "Nein - aktuelle Werte behalten",
        "restore_defaults": "Ja - Standardwerte wiederherstellen",
        "reset_minerva_footer": "Dadurch werden alle neun BitTorrent-Werte geändert",
        "current_value": "Aktuell: {value}",
        "invalid_setting": "Ungültiger Wert für {setting}: {error}",
        "minerva_settings_saved": "MINERVA-EINSTELLUNGEN GESPEICHERT",
        "minerva_settings_saved_message": (
            "Die neuen Werte werden beim nächsten Minerva-Download verwendet."
        ),
        "checking_for_update": "UPDATE WIRD GESUCHT",
        "checking_for_update_message": (
            "Installiert: v{version}\nNeueste GitHub-Version wird gelesen..."
        ),
        "already_up_to_date": "BEREITS AKTUELL",
        "latest_release_message": "v{version} ist die neueste veröffentlichte {target}-Version.",
        "application_update_available": "ANWENDUNGS-UPDATE VERFÜGBAR",
        "download_install_version": "v{version} herunterladen und installieren",
        "later": "Später",
        "installed_published": "Installiert: v{installed}   Veröffentlicht: {published}",
        "installed_application_unchanged": "Die installierte Anwendung wurde nicht geändert.",
        "update_ready": "UPDATE BEREIT",
        "update_ready_message": (
            "v{version} wird jetzt installiert.\n"
            "Öffnen Sie Pocket Harbor danach erneut unter Tools."
        ),
        "connecting_github": "Verbindung zu GitHub wird hergestellt...",
        "cancelling_update": "UPDATE WIRD ABGEBROCHEN",
        "cancelling_update_message": (
            "Unvollständiges Update wird entfernt; die installierte Version bleibt erhalten..."
        ),
        "exit_pocket_harbor": "POCKET HARBOR BEENDEN?",
        "return_to_pocket_harbor": "Nein - zu Pocket Harbor zurückkehren",
        "confirm_exit": "Ja - beenden",
        "exit_footer": "Vor der Rückkehr zu EmulationStation bestätigen",
        "card_number": "KARTE {index}",
        "choose_library_location": "Speicherort der Spielebibliothek auswählen",
        "downloading": "DOWNLOAD LÄUFT",
        "downloaded_kib": "{label}\n{kib} KiB heruntergeladen",
        "cancel_download_footer": "B/Escape: Download abbrechen",
        "connecting_download_service": "Verbindung zum Download-Dienst wird hergestellt...",
        "cancelling_download": "DOWNLOAD WIRD ABGEBROCHEN",
        "cancelling_download_message": (
            "Netzwerkverbindungen werden geschlossen und Teildateien entfernt..."
        ),
        "minerva_torrent_changed": "MINERVA-TORRENT GEÄNDERT",
        "minerva_torrent_changed_message": (
            "Katalogdatei:\n{filename}\nKatalogposition: #{index}\n\nDer Torrent enthält "
            "jetzt {count} Dateien und hat keinen eindeutigen Treffer mehr. Prüfen Sie die "
            "ähnlichsten Kandidaten oder brechen Sie ab; es wurde noch kein Spiel installiert."
        ),
        "minerva_candidate": (
            "#{index}  {filename}  | {size} | {score} % Titelübereinstimmung | {path}"
        ),
        "choose_minerva_torrent_file": "MINERVA-TORRENT-DATEI AUSWÄHLEN",
        "minerva_candidates_footer": "Ähnlichste sichere Kandidaten; B/Escape: abbrechen",
        "review_minerva_file": "MINERVA-DATEI PRÜFEN",
        "review_minerva_file_message": (
            "Im Katalog erwartet:\n{expected}\n\nAusgewählte Torrent-Datei:\n{selected}\n"
            "Torrent-Position: #{index}\nGröße: {size}\nTitelähnlichkeit: {score} %"
        ),
        "confirm_minerva_file": "MINERVA-DATEI BESTÄTIGEN",
        "cancel_download": "Download abbrechen",
        "download_filename": "{filename} herunterladen",
        "confirm_minerva_file_footer": "Nur die ausdrücklich gewählte Torrent-Datei wird geladen",
        "not_detected": "nicht erkannt",
        "not_configured": "nicht konfiguriert",
        "status_title": "POCKET-HARBOR-STATUS",
        "status_message": (
            "Standard-Store: {store}\nStores: {stores}\nZwischenspeicher: {staging}\n"
            "ROM-Stamm: {roms}\nPlattformen: {platforms}\nHardware: {hardware}\n"
            "Kompatibel: {compatible}\nAnzeige: {resolution} Pixel; {width}x{height} "
            "Terminalzellen\nDT-Eingänge: {inputs} ({keys} GPIO-Tasten)\nController: "
            "{controller} (native Linux-Eingabe)\n\nSteuerung\nSteuerkreuz / Sticks / "
            "Pfeile   Auswahl bewegen\nA / Enter        Auswählen\nB / Escape       Zurück\n"
            "X                Suchtext absenden\n\nSuchtext kann mit der eingebauten "
            "Bildschirmtastatur eingegeben werden."
        ),
        "keyboard_letters": "BUCHSTABEN",
        "keyboard_symbols": "SYMBOLE",
        "keyboard_accents": "AKZENTE",
        "operation_failed": "Der Vorgang ist fehlgeschlagen.\nTechnische Details: {error}",
        "terminal_too_small": "Das Terminal muss mindestens 40 Spalten und 15 Zeilen groß sein.",
    },
    "es": {
        "invalid_cache_lifetime": "Introduce una duración válida para la caché del catálogo.",
        "cache_lifetime_range": "Introduce un valor entre 1 y 3650 días.",
        "no_download_stores": "No hay tiendas de descarga activadas. Comprueba PH_STORES.",
        "loading_catalogue": "CARGANDO CATÁLOGO",
        "loading_catalogue_progress": (
            "Leyendo las secciones numéricas y de A a Z...\n{current}/{total}  ({percent} %)"
        ),
        "store_description_vimm": "Archivo de juegos de Vimm",
        "store_description_minerva": "Torrents de RetroAchievements (Python nativo)",
        "compatibility_level_not_listed": "No aparece",
        "compatibility_level_perfect": "Perfecto",
        "compatibility_level_playable": "Jugable",
        "compatibility_level_limited": "Limitado",
        "compatibility_level_unsupported": "No compatible",
        "compatibility_not_listed_source": "No aparece en r36sgamelist.com",
        "compatibility_title_match": "coincidencia del título {score} %",
        "compatibility_title_listed": "título incluido",
        "compatibility_platform_rating": "valoración de la plataforma",
        "compatibility_detail": "{level} ({qualifier})",
        "compatibility_match": "{level} - {score} % de coincidencia",
        "compatibility_listed": "{level} - incluido",
        "destination_platform": "PLATAFORMA DE DESTINO",
        "destination_platform_footer": "El archivo terminado se mueve a esta carpeta de ROM",
        "download_queued": "DESCARGA EN COLA",
        "download_queued_message": (
            "{title}\nDescargando desde {store} en segundo plano. "
            "Abre Descargas para supervisarla o controlarla."
        ),
        "download_queue_empty": "NO HAY DESCARGAS",
        "download_queue_empty_message": "No hay descargas activas ni terminadas recientemente.",
        "download_queue_title": "DESCARGAS",
        "download_queue_footer": "Elige una descarga para pausar, reanudar, reintentar o cancelar",
        "refresh_download_status": "Actualizar estado de descargas",
        "download_state_queued": "En cola",
        "download_state_downloading": "Descargando",
        "download_state_rate_limited": "Esperando para reintentar",
        "download_state_paused": "En pausa",
        "download_state_failed": "Fallida",
        "download_state_cancelled": "Cancelada",
        "download_state_completed": "Completada",
        "download_progress_percent": "{percent}%",
        "download_progress_size": "{size}",
        "download_progress_waiting": "esperando",
        "download_job_row": "{title}  [{state} - {progress}]  {store}",
        "download_store_field": "Tienda: {value}",
        "download_status_field": "Estado: {value}",
        "download_progress_field": "Progreso: {value}",
        "download_error_field": "Error: {value}",
        "download_retry_field": "Reintento automático {attempt} en unos {seconds}s",
        "pause_download": "Pausar descarga",
        "resume_download": "Reanudar descarga",
        "retry_download": "Reintentar descarga",
        "download_details_title": "DETALLES DE DESCARGA",
        "download_controls_footer": "Las descargas conservan su tienda original",
        "download_progress_bytes": "{current} de {total}",
        "confirm_download_cancel": "¿CANCELAR DESCARGA?",
        "keep_downloading": "No - seguir descargando {title}",
        "cancel_and_remove_partial": "Sí - cancelar y borrar datos parciales",
        "cancel_download_warning": "Los datos parciales borrados no se pueden reanudar",
        "detail_url": "URL DE DETALLES",
        "platform_has_no_rom_folder": (
            "Esta plataforma no tiene una carpeta de ROM en el sistema operativo seleccionado."
        ),
        "no_rom_partition_environment": (
            "No se encontró una partición de ROM. Configura PH_ROMS_DIR o PH_ROMS_DIRS."
        ),
        "preparing": "PREPARANDO",
        "retrieving_download_link": "Obteniendo el enlace de descarga...",
        "download_cancelled": "DESCARGA CANCELADA",
        "no_game_installed": "No se instaló ningún juego.",
        "installed_bundled_bios": "Se instalaron {count} archivo(s) BIOS incluidos.",
        "installed_required_bios": (
            "Se instalaron {count} archivo(s) BIOS necesarios desde RetroBIOS."
        ),
        "download_complete": "DESCARGA COMPLETADA",
        "download_complete_message": (
            "{filename}\nMovido a {destination}{bios}\n"
            "La lista de juegos se actualizará al salir de Pocket Harbor."
        ),
        "no_rom_partitions": "No se encontraron particiones de ROM.",
        "choose_memory_card": "ELEGIR TARJETA DE MEMORIA",
        "checking_folders": "COMPROBANDO CARPETAS",
        "finding_installed_platforms": "Buscando plataformas instaladas en {root}...",
        "no_games_on_card": "NO HAY JUEGOS EN LA TARJETA",
        "no_supported_games_on_card": "No se encontraron juegos compatibles en {root}.",
        "choose_installed_platform": "ELEGIR PLATAFORMA INSTALADA",
        "installed_platform_footer": (
            "Las plataformas se detectan rápido; los juegos cargan tras elegir"
        ),
        "scanning_platform": "ESCANEANDO PLATAFORMA",
        "reading_platform": "Leyendo solo {platform} en {root}...",
        "no_games": "NO HAY JUEGOS",
        "no_platform_games": "No se encontraron juegos de {platform}.",
        "platform_on_card": "{platform} EN {root}",
        "manage_games_footer": "A: gestionar   B: atrás   L1/R1: página",
        "refreshing": "ACTUALIZANDO",
        "refreshing_platform": "Actualizando solo {platform}...",
        "card_field": "Tarjeta: {value}",
        "file_field": "Archivo: {value}",
        "files_in_group": "Archivos del grupo: {count}",
        "update_from_remote": "Actualizar desde la tienda",
        "delete_from_device": "Eliminar del dispositivo",
        "manage_game": "GESTIONAR JUEGO",
        "manage_game_footer": "Las actualizaciones conservan la tarjeta y la plataforma",
        "confirm_permanent_delete": "CONFIRMAR ELIMINACIÓN PERMANENTE",
        "keep_game": "No - conservar {title}",
        "delete_files": "Sí - eliminar {count} archivo(s)",
        "delete_warning": "Los archivos eliminados no se pueden recuperar",
        "game_deleted": "JUEGO ELIMINADO",
        "game_deleted_message": (
            "{title}\nLa lista de juegos se actualizará al salir de Pocket Harbor."
        ),
        "store_platform_unsupported": (
            "{store} no admite {platform}. Elige otra tienda en Ajustes."
        ),
        "searching_for_update": "BUSCANDO ACTUALIZACIÓN",
        "no_remote_match": "SIN COINCIDENCIA EN LA TIENDA",
        "choose_replacement": "ELEGIR SUSTITUTO",
        "replacement_footer": "El juego anterior se elimina solo al terminar la descarga",
        "confirm_update": "CONFIRMAR ACTUALIZACIÓN",
        "keep_file": "Cancelar - conservar {filename}",
        "replace_with": "Sustituir por {title}",
        "confirm_choice_footer": "A/Enter: confirmar opción",
        "update_cancelled": "ACTUALIZACIÓN CANCELADA",
        "update_queued": "ACTUALIZACIÓN EN COLA",
        "update_queued_message": (
            "{title}\nEl reemplazo de {store} se descarga en segundo plano. "
            "El juego instalado no cambia hasta que termine."
        ),
        "installed_game_unchanged": "El juego instalado no ha cambiado.",
        "game_updated": "JUEGO ACTUALIZADO",
        "game_updated_message": (
            "{filename}\nInstalado en {destination}{bundled}{required}\n"
            "La lista de juegos se actualizará al salir de Pocket Harbor."
        ),
        "choose_destination_card": "ELEGIR TARJETA DE DESTINO",
        "choose_store_footer": "Elige una tienda de descarga; B/Escape: atrás",
        "first_run_store": "TIENDA DE DESCARGA INICIAL",
        "choose_default_store": "ELEGIR TIENDA PREDETERMINADA",
        "settings_saved": "AJUSTES GUARDADOS",
        "store_saved_message": "Las búsquedas, descargas y actualizaciones usarán {store}.",
        "store_cached_count": "{store}  [{count} en caché]",
        "cache_invalid": "caché no válida",
        "stale_over_days": "caducada (>{days} días)",
        "fresh": "actual",
        "connecting_retrobios": "Conectando con RetroBIOS...",
        "finding_retrobios_revision": "Buscando la revisión más reciente de RetroBIOS",
        "downloading_retrobios_profiles": "Descargando perfiles de núcleos de RetroBIOS",
        "retrobios_update_title": "¿ACTUALIZAR EL CATÁLOGO RETROBIOS?",
        "download_latest_metadata": "Descargar los metadatos más recientes",
        "catalogue_unchanged": "El catálogo existente no ha cambiado.",
        "retrobios_update_cancelled": "ACTUALIZACIÓN RETROBIOS CANCELADA",
        "retrobios_updated": "RETROBIOS ACTUALIZADO",
        "retrobios_summary": (
            "Revisión: {revision}\nSistemas: {systems}\nPerfil de RetroArch: {profile}"
        ),
        "unknown": "desconocido",
        "choose_bios_memory_card": "ELEGIR TARJETA DE MEMORIA PARA BIOS",
        "no_rom_partition": "No se encontró ninguna partición de ROM.",
        "search_bios_title": "BUSCAR BIOS",
        "search_bios_empty_hint": "HECHO sin texto: mostrar todo el catálogo de BIOS",
        "no_bios_results": "SIN RESULTADOS DE BIOS",
        "bios_catalogue_empty": "El catálogo de BIOS está vacío.",
        "bios_results": "RESULTADOS DE BIOS ({count})",
        "bios_results_footer": "Elige una BIOS para verla o descargarla; B/Escape: atrás",
        "bios_details": "DETALLES DE LA BIOS",
        "platform_field": "Plataforma: {value}",
        "status_field": "Estado: {value}",
        "required": "Obligatoria",
        "optional": "Opcional",
        "required_short": "O",
        "optional_short": "P",
        "all_regions": "todas",
        "destination_field": "Destino: {value}",
        "bios_state_valid": "válida",
        "bios_state_missing": "ausente",
        "bios_state_invalid": "no válida",
        "bios_entry_not_downloadable": (
            "RetroBIOS tiene metadatos, pero no un archivo descargable para esta entrada."
        ),
        "bios_check_unavailable": "COMPROBACIÓN DE BIOS NO DISPONIBLE",
        "bios_check_unavailable_message": (
            "El juego se instaló, pero no se pudieron cargar los metadatos de RetroBIOS:\n"
            "{error}\nPuedes volver a intentarlo desde Buscar y descargar BIOS."
        ),
        "required_bios_not_found": "NO SE ENCONTRÓ LA BIOS NECESARIA",
        "required_bios_missing_message": (
            "El archivo del juego no incluía estas BIOS necesarias y no se encontró una "
            "copia válida en ninguna tarjeta de memoria:"
        ),
        "and_more": "...y {count} más",
        "download_required_bios": "¿DESCARGAR LAS BIOS NECESARIAS?",
        "download_from_retrobios": "Descargar desde RetroBIOS",
        "keep_without_bios": "Conservar el juego sin BIOS",
        "firmware_warning": "Es posible que el juego no arranque sin el firmware necesario",
        "bios_not_downloadable": "BIOS NO DESCARGABLE",
        "bios_not_downloadable_message": (
            "RetroBIOS tiene metadatos del requisito, pero no una copia descargable de los "
            "archivos seleccionados."
        ),
        "confirm_retrobios_download": "CONFIRMAR DESCARGA DE RETROBIOS",
        "download_verified_bios": "Descargar {count} archivo(s) BIOS verificados",
        "bios_legal_footer": (
            "Continúa solo si tienes permiso para obtener estas copias de seguridad personales"
        ),
        "bios_download_cancelled": "DESCARGA DE BIOS CANCELADA",
        "no_incomplete_bios_installed": "No se instaló ningún archivo BIOS incompleto.",
        "bios_installed": "BIOS INSTALADA",
        "bios_installed_message": (
            "Se instalaron y verificaron {count} archivo(s) BIOS en {destination}."
        ),
        "minerva_settings_title": "AJUSTES BITTORRENT DE MINERVA",
        "minerva_udp_protocol_id": "ID del protocolo UDP",
        "minerva_block_size": "Tamaño de bloque (bytes)",
        "minerva_max_torrent_bytes": "Máx. metadatos del torrent (bytes)",
        "minerva_max_tracker_bytes": "Máx. respuesta del tracker (bytes)",
        "minerva_max_peer_attempts": "Máx. intentos de pares",
        "minerva_peer_race_workers": "Búsquedas de pares en paralelo",
        "minerva_max_peer_timeout": "Tiempo máx. del par (segundos)",
        "minerva_max_tracker_queries": "Máx. consultas al tracker",
        "minerva_max_discovered_peers": "Máx. pares encontrados",
        "reset_all_defaults": "Restablecer todos los valores",
        "minerva_settings_footer": "Los valores avanzados se guardan localmente",
        "reset_minerva_settings": "¿RESTABLECER LOS AJUSTES DE MINERVA?",
        "keep_current_values": "No - conservar los valores actuales",
        "restore_defaults": "Sí - restaurar valores predeterminados",
        "reset_minerva_footer": "Esto cambia los nueve valores de BitTorrent",
        "current_value": "Actual: {value}",
        "invalid_setting": "Valor no válido para {setting}: {error}",
        "minerva_settings_saved": "AJUSTES DE MINERVA GUARDADOS",
        "minerva_settings_saved_message": (
            "Los nuevos valores se usarán en la próxima descarga de Minerva."
        ),
        "checking_for_update": "BUSCANDO ACTUALIZACIÓN",
        "checking_for_update_message": (
            "Instalada: v{version}\nLeyendo la versión más reciente de GitHub..."
        ),
        "already_up_to_date": "YA ESTÁ ACTUALIZADA",
        "latest_release_message": "v{version} es la última versión publicada para {target}.",
        "application_update_available": "ACTUALIZACIÓN DE LA APLICACIÓN DISPONIBLE",
        "download_install_version": "Descargar e instalar v{version}",
        "later": "Más tarde",
        "installed_published": "Instalada: v{installed}   Publicada: {published}",
        "installed_application_unchanged": "La aplicación instalada no ha cambiado.",
        "update_ready": "ACTUALIZACIÓN LISTA",
        "update_ready_message": (
            "v{version} se instalará ahora.\n"
            "Vuelve a abrir Pocket Harbor desde Herramientas al cerrar esta pantalla."
        ),
        "connecting_github": "Conectando con GitHub...",
        "cancelling_update": "CANCELANDO ACTUALIZACIÓN",
        "cancelling_update_message": (
            "Eliminando la actualización incompleta; la versión instalada no cambia..."
        ),
        "exit_pocket_harbor": "¿SALIR DE POCKET HARBOR?",
        "return_to_pocket_harbor": "No - volver a Pocket Harbor",
        "confirm_exit": "Sí - salir",
        "exit_footer": "Confirma antes de volver a EmulationStation",
        "card_number": "TARJETA {index}",
        "choose_library_location": "Elige dónde está guardada la biblioteca de juegos",
        "downloading": "DESCARGANDO",
        "downloaded_kib": "{label}\n{kib} KiB descargados",
        "cancel_download_footer": "B/Escape: cancelar descarga",
        "connecting_download_service": "Conectando con el servicio de descarga...",
        "cancelling_download": "CANCELANDO DESCARGA",
        "cancelling_download_message": (
            "Cerrando conexiones de red y eliminando archivos parciales..."
        ),
        "minerva_torrent_changed": "EL TORRENT DE MINERVA HA CAMBIADO",
        "minerva_torrent_changed_message": (
            "Archivo del catálogo:\n{filename}\nPosición en el catálogo: #{index}\n\nEl torrent "
            "contiene ahora {count} archivos y ya no tiene una coincidencia inequívoca. "
            "Revisa los candidatos más cercanos o cancela; aún no se ha instalado ningún juego."
        ),
        "minerva_candidate": (
            "#{index}  {filename}  | {size} | {score} % de coincidencia | {path}"
        ),
        "choose_minerva_torrent_file": "ELEGIR ARCHIVO DEL TORRENT DE MINERVA",
        "minerva_candidates_footer": "Candidatos seguros más cercanos; B/Escape: cancelar",
        "review_minerva_file": "REVISAR ARCHIVO DE MINERVA",
        "review_minerva_file_message": (
            "Esperado por el catálogo:\n{expected}\n\nArchivo torrent seleccionado:\n{selected}\n"
            "Posición en el torrent: #{index}\nTamaño: {size}\nSimilitud del título: {score} %"
        ),
        "confirm_minerva_file": "CONFIRMAR ARCHIVO DE MINERVA",
        "cancel_download": "Cancelar descarga",
        "download_filename": "Descargar {filename}",
        "confirm_minerva_file_footer": "Solo se descargará el archivo torrent seleccionado",
        "not_detected": "no detectado",
        "not_configured": "sin configurar",
        "status_title": "ESTADO DE POCKET HARBOR",
        "status_message": (
            "Tienda predeterminada: {store}\nTiendas: {stores}\nDescargas temporales: {staging}\n"
            "Raíz de ROM: {roms}\nPlataformas: {platforms}\nHardware: {hardware}\n"
            "Compatible: {compatible}\nPantalla: {resolution} píxeles; {width}x{height} celdas "
            "de terminal\nEntradas DT: {inputs} ({keys} teclas GPIO)\nMando: {controller} "
            "(entrada nativa de Linux)\n\nControles\nCruceta / sticks / flechas   Mover "
            "selección\nA / Enter        Seleccionar\nB / Escape       Volver\n"
            "X                Enviar texto de búsqueda\n\nEl texto se puede introducir con "
            "el teclado integrado en pantalla."
        ),
        "keyboard_letters": "LETRAS",
        "keyboard_symbols": "SÍMBOLOS",
        "keyboard_accents": "ACENTOS",
        "operation_failed": "La operación ha fallado.\nDetalles técnicos: {error}",
        "terminal_too_small": "El terminal debe tener al menos 40 columnas y 15 filas.",
    },
    "it": {
        "invalid_cache_lifetime": "Inserisci una durata valida per la cache del catalogo.",
        "cache_lifetime_range": "Inserisci un valore compreso tra 1 e 3650 giorni.",
        "no_download_stores": "Non è abilitato alcuno store. Controlla PH_STORES.",
        "loading_catalogue": "CARICAMENTO CATALOGO",
        "loading_catalogue_progress": (
            "Lettura delle sezioni numeriche e A-Z...\n{current}/{total}  ({percent}%)"
        ),
        "store_description_vimm": "Archivio giochi Vimm",
        "store_description_minerva": "Torrent RetroAchievements (Python nativo)",
        "compatibility_level_not_listed": "Non presente",
        "compatibility_level_perfect": "Perfetta",
        "compatibility_level_playable": "Giocabile",
        "compatibility_level_limited": "Limitata",
        "compatibility_level_unsupported": "Non supportata",
        "compatibility_not_listed_source": "Non presente su r36sgamelist.com",
        "compatibility_title_match": "corrispondenza titolo {score}%",
        "compatibility_title_listed": "titolo presente",
        "compatibility_platform_rating": "valutazione piattaforma",
        "compatibility_detail": "{level} ({qualifier})",
        "compatibility_match": "{level} - corrispondenza {score}%",
        "compatibility_listed": "{level} - presente",
        "destination_platform": "PIATTAFORMA DI DESTINAZIONE",
        "destination_platform_footer": "Il file completato viene spostato in questa cartella ROM",
        "download_queued": "DOWNLOAD IN CODA",
        "download_queued_message": (
            "{title}\nDownload da {store} in background. "
            "Apri Download per monitorarlo o controllarlo."
        ),
        "download_queue_empty": "NESSUN DOWNLOAD",
        "download_queue_empty_message": "Non ci sono download attivi o completati di recente.",
        "download_queue_title": "DOWNLOAD",
        "download_queue_footer": (
            "Seleziona un download per sospendere, riprendere, riprovare o annullare"
        ),
        "refresh_download_status": "Aggiorna stato download",
        "download_state_queued": "In coda",
        "download_state_downloading": "In download",
        "download_state_rate_limited": "In attesa di riprovare",
        "download_state_paused": "In pausa",
        "download_state_failed": "Non riuscito",
        "download_state_cancelled": "Annullato",
        "download_state_completed": "Completato",
        "download_progress_percent": "{percent}%",
        "download_progress_size": "{size}",
        "download_progress_waiting": "in attesa",
        "download_job_row": "{title}  [{state} - {progress}]  {store}",
        "download_store_field": "Store: {value}",
        "download_status_field": "Stato: {value}",
        "download_progress_field": "Progresso: {value}",
        "download_error_field": "Errore: {value}",
        "download_retry_field": "Tentativo automatico {attempt} tra circa {seconds}s",
        "pause_download": "Sospendi download",
        "resume_download": "Riprendi download",
        "retry_download": "Riprova download",
        "download_details_title": "DETTAGLI DOWNLOAD",
        "download_controls_footer": "I download mantengono lo store originale",
        "download_progress_bytes": "{current} di {total}",
        "confirm_download_cancel": "ANNULLARE IL DOWNLOAD?",
        "keep_downloading": "No - continua a scaricare {title}",
        "cancel_and_remove_partial": "Sì - annulla e rimuovi i dati parziali",
        "cancel_download_warning": "I dati parziali rimossi non possono essere ripresi",
        "detail_url": "URL DETTAGLI",
        "platform_has_no_rom_folder": (
            "Questa piattaforma non ha una cartella ROM sul sistema operativo selezionato."
        ),
        "no_rom_partition_environment": (
            "Nessuna partizione ROM trovata. Imposta PH_ROMS_DIR o PH_ROMS_DIRS."
        ),
        "preparing": "PREPARAZIONE",
        "retrieving_download_link": "Recupero del link di download...",
        "download_cancelled": "DOWNLOAD ANNULLATO",
        "no_game_installed": "Nessun gioco è stato installato.",
        "installed_bundled_bios": "Installati {count} file BIOS inclusi.",
        "installed_required_bios": ("Installati {count} file BIOS necessari da RetroBIOS."),
        "download_complete": "DOWNLOAD COMPLETATO",
        "download_complete_message": (
            "{filename}\nSpostato in {destination}{bios}\n"
            "La lista dei giochi verrà aggiornata all'uscita da Pocket Harbor."
        ),
        "no_rom_partitions": "Nessuna partizione ROM trovata.",
        "choose_memory_card": "SCEGLI SCHEDA DI MEMORIA",
        "checking_folders": "CONTROLLO CARTELLE",
        "finding_installed_platforms": "Ricerca delle piattaforme installate su {root}...",
        "no_games_on_card": "NESSUN GIOCO SULLA SCHEDA",
        "no_supported_games_on_card": "Nessun gioco supportato trovato su {root}.",
        "choose_installed_platform": "SCEGLI PIATTAFORMA INSTALLATA",
        "installed_platform_footer": (
            "Le piattaforme vengono rilevate rapidamente; i giochi caricano dopo la scelta"
        ),
        "scanning_platform": "SCANSIONE PIATTAFORMA",
        "reading_platform": "Lettura del solo {platform} su {root}...",
        "no_games": "NESSUN GIOCO",
        "no_platform_games": "Nessun gioco {platform} trovato.",
        "platform_on_card": "{platform} SU {root}",
        "manage_games_footer": "A: gestisci   B: indietro   L1/R1: pagina",
        "refreshing": "AGGIORNAMENTO",
        "refreshing_platform": "Aggiornamento del solo {platform}...",
        "card_field": "Scheda: {value}",
        "file_field": "File: {value}",
        "files_in_group": "File nel gruppo: {count}",
        "update_from_remote": "Aggiorna dallo store",
        "delete_from_device": "Elimina dal dispositivo",
        "manage_game": "GESTISCI GIOCO",
        "manage_game_footer": "Gli aggiornamenti mantengono scheda e piattaforma",
        "confirm_permanent_delete": "CONFERMA ELIMINAZIONE DEFINITIVA",
        "keep_game": "No - mantieni {title}",
        "delete_files": "Sì - elimina {count} file",
        "delete_warning": "I file eliminati non possono essere recuperati",
        "game_deleted": "GIOCO ELIMINATO",
        "game_deleted_message": (
            "{title}\nLa lista dei giochi verrà aggiornata all'uscita da Pocket Harbor."
        ),
        "store_platform_unsupported": (
            "{store} non supporta {platform}. Scegli un altro store nelle Impostazioni."
        ),
        "searching_for_update": "RICERCA AGGIORNAMENTO",
        "no_remote_match": "NESSUNA CORRISPONDENZA NELLO STORE",
        "choose_replacement": "SCEGLI SOSTITUZIONE",
        "replacement_footer": "Il vecchio gioco viene rimosso solo al termine del download",
        "confirm_update": "CONFERMA AGGIORNAMENTO",
        "keep_file": "Annulla - mantieni {filename}",
        "replace_with": "Sostituisci con {title}",
        "confirm_choice_footer": "A/Invio: conferma scelta",
        "update_cancelled": "AGGIORNAMENTO ANNULLATO",
        "update_queued": "AGGIORNAMENTO IN CODA",
        "update_queued_message": (
            "{title}\nLa sostituzione da {store} viene scaricata in background. "
            "Il gioco installato resta invariato fino al completamento."
        ),
        "installed_game_unchanged": "Il gioco installato non è stato modificato.",
        "game_updated": "GIOCO AGGIORNATO",
        "game_updated_message": (
            "{filename}\nInstallato su {destination}{bundled}{required}\n"
            "La lista dei giochi verrà aggiornata all'uscita da Pocket Harbor."
        ),
        "choose_destination_card": "SCEGLI SCHEDA DI DESTINAZIONE",
        "choose_store_footer": "Scegli uno store; B/Escape: indietro",
        "first_run_store": "STORE DI DOWNLOAD INIZIALE",
        "choose_default_store": "SCEGLI STORE PREDEFINITO",
        "settings_saved": "IMPOSTAZIONI SALVATE",
        "store_saved_message": "Ricerche, download e aggiornamenti useranno {store}.",
        "store_cached_count": "{store}  [{count} in cache]",
        "cache_invalid": "cache non valida",
        "stale_over_days": "scaduta (>{days} giorni)",
        "fresh": "aggiornata",
        "connecting_retrobios": "Connessione a RetroBIOS...",
        "finding_retrobios_revision": "Ricerca dell'ultima revisione RetroBIOS",
        "downloading_retrobios_profiles": "Download dei profili core RetroBIOS",
        "retrobios_update_title": "AGGIORNARE IL CATALOGO RETROBIOS?",
        "download_latest_metadata": "Scarica i metadati più recenti",
        "catalogue_unchanged": "Il catalogo esistente non è stato modificato.",
        "retrobios_update_cancelled": "AGGIORNAMENTO RETROBIOS ANNULLATO",
        "retrobios_updated": "RETROBIOS AGGIORNATO",
        "retrobios_summary": (
            "Revisione: {revision}\nSistemi: {systems}\nProfilo RetroArch: {profile}"
        ),
        "unknown": "sconosciuto",
        "choose_bios_memory_card": "SCEGLI SCHEDA DI MEMORIA BIOS",
        "no_rom_partition": "Nessuna partizione ROM trovata.",
        "search_bios_title": "CERCA BIOS",
        "search_bios_empty_hint": "FINE senza testo: mostra l'intero catalogo BIOS",
        "no_bios_results": "NESSUN RISULTATO BIOS",
        "bios_catalogue_empty": "Il catalogo BIOS è vuoto.",
        "bios_results": "RISULTATI BIOS ({count})",
        "bios_results_footer": "Scegli un BIOS da esaminare o scaricare; B/Escape: indietro",
        "bios_details": "DETTAGLI BIOS",
        "platform_field": "Piattaforma: {value}",
        "status_field": "Stato: {value}",
        "required": "Necessario",
        "optional": "Opzionale",
        "required_short": "N",
        "optional_short": "O",
        "all_regions": "tutte",
        "destination_field": "Destinazione: {value}",
        "bios_state_valid": "valido",
        "bios_state_missing": "mancante",
        "bios_state_invalid": "non valido",
        "bios_entry_not_downloadable": (
            "RetroBIOS contiene i metadati ma nessun file scaricabile per questa voce."
        ),
        "bios_check_unavailable": "CONTROLLO BIOS NON DISPONIBILE",
        "bios_check_unavailable_message": (
            "Il gioco è stato installato, ma non è stato possibile caricare i metadati "
            "RetroBIOS:\n{error}\nPuoi riprovare da Cerca e scarica BIOS."
        ),
        "required_bios_not_found": "BIOS NECESSARIO NON TROVATO",
        "required_bios_missing_message": (
            "L'archivio del gioco non conteneva questi file BIOS necessari e non è stata "
            "trovata una copia valida su nessuna scheda di memoria:"
        ),
        "and_more": "...e altri {count}",
        "download_required_bios": "SCARICARE I BIOS NECESSARI?",
        "download_from_retrobios": "Scarica da RetroBIOS",
        "keep_without_bios": "Mantieni il gioco senza BIOS",
        "firmware_warning": "Il gioco potrebbe non avviarsi senza il firmware necessario",
        "bios_not_downloadable": "BIOS NON SCARICABILE",
        "bios_not_downloadable_message": (
            "RetroBIOS contiene i metadati dei requisiti ma non una copia scaricabile dei "
            "file selezionati."
        ),
        "confirm_retrobios_download": "CONFERMA DOWNLOAD RETROBIOS",
        "download_verified_bios": "Scarica {count} file BIOS verificati",
        "bios_legal_footer": (
            "Continua solo se sei autorizzato a ottenere queste copie di sicurezza personali"
        ),
        "bios_download_cancelled": "DOWNLOAD BIOS ANNULLATO",
        "no_incomplete_bios_installed": "Nessun file BIOS incompleto è stato installato.",
        "bios_installed": "BIOS INSTALLATO",
        "bios_installed_message": ("Installati e verificati {count} file BIOS in {destination}."),
        "minerva_settings_title": "IMPOSTAZIONI BITTORRENT MINERVA",
        "minerva_udp_protocol_id": "ID protocollo UDP",
        "minerva_block_size": "Dimensione blocco (byte)",
        "minerva_max_torrent_bytes": "Metadati torrent massimi (byte)",
        "minerva_max_tracker_bytes": "Risposta tracker massima (byte)",
        "minerva_max_peer_attempts": "Tentativi peer massimi",
        "minerva_peer_race_workers": "Ricerche peer parallele",
        "minerva_max_peer_timeout": "Timeout peer massimo (secondi)",
        "minerva_max_tracker_queries": "Richieste tracker massime",
        "minerva_max_discovered_peers": "Peer rilevati massimi",
        "reset_all_defaults": "Ripristina tutti i valori predefiniti",
        "minerva_settings_footer": "I valori avanzati vengono salvati localmente",
        "reset_minerva_settings": "RIPRISTINARE LE IMPOSTAZIONI MINERVA?",
        "keep_current_values": "No - mantieni i valori attuali",
        "restore_defaults": "Sì - ripristina i valori predefiniti",
        "reset_minerva_footer": "Questo modifica tutti i nove valori BitTorrent",
        "current_value": "Attuale: {value}",
        "invalid_setting": "Valore non valido per {setting}: {error}",
        "minerva_settings_saved": "IMPOSTAZIONI MINERVA SALVATE",
        "minerva_settings_saved_message": (
            "I nuovi valori verranno usati dal prossimo download Minerva."
        ),
        "checking_for_update": "CONTROLLO AGGIORNAMENTI",
        "checking_for_update_message": (
            "Installata: v{version}\nLettura dell'ultima versione GitHub..."
        ),
        "already_up_to_date": "GIÀ AGGIORNATO",
        "latest_release_message": "v{version} è l'ultima versione {target} pubblicata.",
        "application_update_available": "AGGIORNAMENTO APPLICAZIONE DISPONIBILE",
        "download_install_version": "Scarica e installa v{version}",
        "later": "Più tardi",
        "installed_published": "Installata: v{installed}   Pubblicata: {published}",
        "installed_application_unchanged": "L'applicazione installata non è stata modificata.",
        "update_ready": "AGGIORNAMENTO PRONTO",
        "update_ready_message": (
            "v{version} verrà installata ora.\n"
            "Riapri Pocket Harbor da Strumenti dopo la chiusura di questa schermata."
        ),
        "connecting_github": "Connessione a GitHub...",
        "cancelling_update": "ANNULLAMENTO AGGIORNAMENTO",
        "cancelling_update_message": (
            "Rimozione dell'aggiornamento incompleto; la versione installata non cambia..."
        ),
        "exit_pocket_harbor": "USCIRE DA POCKET HARBOR?",
        "return_to_pocket_harbor": "No - torna a Pocket Harbor",
        "confirm_exit": "Sì - esci",
        "exit_footer": "Conferma prima di tornare a EmulationStation",
        "card_number": "SCHEDA {index}",
        "choose_library_location": "Scegli dove è memorizzata la libreria dei giochi",
        "downloading": "DOWNLOAD IN CORSO",
        "downloaded_kib": "{label}\n{kib} KiB scaricati",
        "cancel_download_footer": "B/Escape: annulla download",
        "connecting_download_service": "Connessione al servizio di download...",
        "cancelling_download": "ANNULLAMENTO DOWNLOAD",
        "cancelling_download_message": (
            "Chiusura delle connessioni di rete e rimozione dei file parziali..."
        ),
        "minerva_torrent_changed": "TORRENT MINERVA MODIFICATO",
        "minerva_torrent_changed_message": (
            "File del catalogo:\n{filename}\nPosizione nel catalogo: #{index}\n\nIl torrent ora "
            "contiene {count} file e non ha più una corrispondenza univoca. Esamina i "
            "candidati più vicini o annulla; nessun gioco è stato ancora installato."
        ),
        "minerva_candidate": (
            "#{index}  {filename}  | {size} | {score}% corrispondenza titolo | {path}"
        ),
        "choose_minerva_torrent_file": "SCEGLI FILE TORRENT MINERVA",
        "minerva_candidates_footer": "Candidati sicuri più vicini; B/Escape: annulla",
        "review_minerva_file": "ESAMINA FILE MINERVA",
        "review_minerva_file_message": (
            "Previsto dal catalogo:\n{expected}\n\nFile torrent selezionato:\n{selected}\n"
            "Posizione nel torrent: #{index}\nDimensione: {size}\nSomiglianza titolo: {score}%"
        ),
        "confirm_minerva_file": "CONFERMA FILE MINERVA",
        "cancel_download": "Annulla download",
        "download_filename": "Scarica {filename}",
        "confirm_minerva_file_footer": "Verrà scaricato solo il file torrent selezionato",
        "not_detected": "non rilevato",
        "not_configured": "non configurato",
        "status_title": "STATO DI POCKET HARBOR",
        "status_message": (
            "Store predefinito: {store}\nStore: {stores}\nArea download: {staging}\n"
            "Radice ROM: {roms}\nPiattaforme: {platforms}\nHardware: {hardware}\n"
            "Compatibile: {compatible}\nSchermo: {resolution} pixel; {width}x{height} celle "
            "del terminale\nIngressi DT: {inputs} ({keys} tasti GPIO)\nController: {controller} "
            "(input Linux nativo)\n\nControlli\nD-pad / stick / frecce   Sposta selezione\n"
            "A / Invio        Seleziona\nB / Escape       Indietro\n"
            "X                Conferma testo di ricerca\n\nIl testo può essere inserito con "
            "la tastiera integrata sullo schermo."
        ),
        "keyboard_letters": "LETTERE",
        "keyboard_symbols": "SIMBOLI",
        "keyboard_accents": "ACCENTI",
        "operation_failed": "L'operazione non è riuscita.\nDettagli tecnici: {error}",
        "terminal_too_small": "Il terminale deve avere almeno 40 colonne e 15 righe.",
    },
    "pt": {
        "invalid_cache_lifetime": "Introduza uma duração válida para a cache do catálogo.",
        "cache_lifetime_range": "Introduza um valor entre 1 e 3650 dias.",
        "no_download_stores": "Não há lojas de transferência ativas. Verifique PH_STORES.",
        "loading_catalogue": "A CARREGAR CATÁLOGO",
        "loading_catalogue_progress": (
            "A ler as secções numéricas e A-Z...\n{current}/{total}  ({percent}%)"
        ),
        "store_description_vimm": "Arquivo de jogos Vimm",
        "store_description_minerva": "Torrents RetroAchievements (Python nativo)",
        "compatibility_level_not_listed": "Não listado",
        "compatibility_level_perfect": "Perfeito",
        "compatibility_level_playable": "Jogável",
        "compatibility_level_limited": "Limitado",
        "compatibility_level_unsupported": "Não suportado",
        "compatibility_not_listed_source": "Não listado em r36sgamelist.com",
        "compatibility_title_match": "correspondência do título {score}%",
        "compatibility_title_listed": "título listado",
        "compatibility_platform_rating": "classificação da plataforma",
        "compatibility_detail": "{level} ({qualifier})",
        "compatibility_match": "{level} - {score}% de correspondência",
        "compatibility_listed": "{level} - listado",
        "destination_platform": "PLATAFORMA DE DESTINO",
        "destination_platform_footer": "O ficheiro concluído é movido para esta pasta de ROM",
        "download_queued": "TRANSFERÊNCIA EM FILA",
        "download_queued_message": (
            "{title}\nA transferir de {store} em segundo plano. "
            "Abra Transferências para acompanhar ou controlar."
        ),
        "download_queue_empty": "SEM TRANSFERÊNCIAS",
        "download_queue_empty_message": "Não há transferências ativas ou concluídas recentemente.",
        "download_queue_title": "TRANSFERÊNCIAS",
        "download_queue_footer": "Selecione para pausar, retomar, repetir ou cancelar",
        "refresh_download_status": "Atualizar estado das transferências",
        "download_state_queued": "Em fila",
        "download_state_downloading": "A transferir",
        "download_state_rate_limited": "A aguardar nova tentativa",
        "download_state_paused": "Pausada",
        "download_state_failed": "Falhou",
        "download_state_cancelled": "Cancelada",
        "download_state_completed": "Concluída",
        "download_progress_percent": "{percent}%",
        "download_progress_size": "{size}",
        "download_progress_waiting": "a aguardar",
        "download_job_row": "{title}  [{state} - {progress}]  {store}",
        "download_store_field": "Loja: {value}",
        "download_status_field": "Estado: {value}",
        "download_progress_field": "Progresso: {value}",
        "download_error_field": "Erro: {value}",
        "download_retry_field": "Tentativa automática {attempt} dentro de cerca de {seconds}s",
        "pause_download": "Pausar transferência",
        "resume_download": "Retomar transferência",
        "retry_download": "Repetir transferência",
        "download_details_title": "DETALHES DA TRANSFERÊNCIA",
        "download_controls_footer": "As transferências mantêm a loja original",
        "download_progress_bytes": "{current} de {total}",
        "confirm_download_cancel": "CANCELAR TRANSFERÊNCIA?",
        "keep_downloading": "Não - continuar a transferir {title}",
        "cancel_and_remove_partial": "Sim - cancelar e remover dados parciais",
        "cancel_download_warning": "Os dados parciais removidos não podem ser retomados",
        "detail_url": "URL DE DETALHES",
        "platform_has_no_rom_folder": (
            "Esta plataforma não tem uma pasta de ROM no sistema operativo selecionado."
        ),
        "no_rom_partition_environment": (
            "Não foi encontrada uma partição de ROM. Defina PH_ROMS_DIR ou PH_ROMS_DIRS."
        ),
        "preparing": "A PREPARAR",
        "retrieving_download_link": "A obter a ligação de transferência...",
        "download_cancelled": "TRANSFERÊNCIA CANCELADA",
        "no_game_installed": "Nenhum jogo foi instalado.",
        "installed_bundled_bios": "Instalados {count} ficheiro(s) BIOS incluídos.",
        "installed_required_bios": (
            "Instalados {count} ficheiro(s) BIOS necessários do RetroBIOS."
        ),
        "download_complete": "TRANSFERÊNCIA CONCLUÍDA",
        "download_complete_message": (
            "{filename}\nMovido para {destination}{bios}\n"
            "A lista de jogos será atualizada ao sair do Pocket Harbor."
        ),
        "no_rom_partitions": "Não foram encontradas partições de ROM.",
        "choose_memory_card": "ESCOLHER CARTÃO DE MEMÓRIA",
        "checking_folders": "A VERIFICAR PASTAS",
        "finding_installed_platforms": "A procurar plataformas instaladas em {root}...",
        "no_games_on_card": "SEM JOGOS NO CARTÃO",
        "no_supported_games_on_card": "Não foram encontrados jogos suportados em {root}.",
        "choose_installed_platform": "ESCOLHER PLATAFORMA INSTALADA",
        "installed_platform_footer": (
            "As plataformas são detetadas rapidamente; os jogos carregam após a seleção"
        ),
        "scanning_platform": "A ANALISAR PLATAFORMA",
        "reading_platform": "A ler apenas {platform} em {root}...",
        "no_games": "SEM JOGOS",
        "no_platform_games": "Não foram encontrados jogos de {platform}.",
        "platform_on_card": "{platform} EM {root}",
        "manage_games_footer": "A: gerir   B: voltar   L1/R1: página",
        "refreshing": "A ATUALIZAR",
        "refreshing_platform": "A atualizar apenas {platform}...",
        "card_field": "Cartão: {value}",
        "file_field": "Ficheiro: {value}",
        "files_in_group": "Ficheiros no grupo: {count}",
        "update_from_remote": "Atualizar a partir da loja",
        "delete_from_device": "Eliminar do dispositivo",
        "manage_game": "GERIR JOGO",
        "manage_game_footer": "As atualizações mantêm o cartão e a plataforma",
        "confirm_permanent_delete": "CONFIRMAR ELIMINAÇÃO PERMANENTE",
        "keep_game": "Não - manter {title}",
        "delete_files": "Sim - eliminar {count} ficheiro(s)",
        "delete_warning": "Os ficheiros eliminados não podem ser recuperados",
        "game_deleted": "JOGO ELIMINADO",
        "game_deleted_message": (
            "{title}\nA lista de jogos será atualizada ao sair do Pocket Harbor."
        ),
        "store_platform_unsupported": (
            "{store} não suporta {platform}. Escolha outra loja nas Definições."
        ),
        "searching_for_update": "A PROCURAR ATUALIZAÇÃO",
        "no_remote_match": "SEM CORRESPONDÊNCIA NA LOJA",
        "choose_replacement": "ESCOLHER SUBSTITUTO",
        "replacement_footer": "O jogo antigo só é removido após a transferência terminar",
        "confirm_update": "CONFIRMAR ATUALIZAÇÃO",
        "keep_file": "Cancelar - manter {filename}",
        "replace_with": "Substituir por {title}",
        "confirm_choice_footer": "A/Enter: confirmar escolha",
        "update_cancelled": "ATUALIZAÇÃO CANCELADA",
        "update_queued": "ATUALIZAÇÃO EM FILA",
        "update_queued_message": (
            "{title}\nA substituição de {store} é transferida em segundo plano. "
            "O jogo instalado permanece inalterado até à conclusão."
        ),
        "installed_game_unchanged": "O jogo instalado não foi alterado.",
        "game_updated": "JOGO ATUALIZADO",
        "game_updated_message": (
            "{filename}\nInstalado em {destination}{bundled}{required}\n"
            "A lista de jogos será atualizada ao sair do Pocket Harbor."
        ),
        "choose_destination_card": "ESCOLHER CARTÃO DE DESTINO",
        "choose_store_footer": "Escolha uma loja; B/Escape: voltar",
        "first_run_store": "LOJA DE TRANSFERÊNCIA INICIAL",
        "choose_default_store": "ESCOLHER LOJA PREDEFINIDA",
        "settings_saved": "DEFINIÇÕES GUARDADAS",
        "store_saved_message": "Pesquisas, transferências e atualizações usarão {store}.",
        "store_cached_count": "{store}  [{count} em cache]",
        "cache_invalid": "cache inválida",
        "stale_over_days": "expirada (>{days} dias)",
        "fresh": "atual",
        "connecting_retrobios": "A ligar ao RetroBIOS...",
        "finding_retrobios_revision": "A procurar a revisão mais recente do RetroBIOS",
        "downloading_retrobios_profiles": "A transferir perfis de núcleos RetroBIOS",
        "retrobios_update_title": "ATUALIZAR O CATÁLOGO RETROBIOS?",
        "download_latest_metadata": "Transferir os metadados mais recentes",
        "catalogue_unchanged": "O catálogo existente não foi alterado.",
        "retrobios_update_cancelled": "ATUALIZAÇÃO RETROBIOS CANCELADA",
        "retrobios_updated": "RETROBIOS ATUALIZADO",
        "retrobios_summary": (
            "Revisão: {revision}\nSistemas: {systems}\nPerfil RetroArch: {profile}"
        ),
        "unknown": "desconhecido",
        "choose_bios_memory_card": "ESCOLHER CARTÃO DE MEMÓRIA PARA BIOS",
        "no_rom_partition": "Não foi encontrada uma partição de ROM.",
        "search_bios_title": "PESQUISAR BIOS",
        "search_bios_empty_hint": "CONCLUIR sem texto: mostrar todo o catálogo BIOS",
        "no_bios_results": "SEM RESULTADOS DE BIOS",
        "bios_catalogue_empty": "O catálogo BIOS está vazio.",
        "bios_results": "RESULTADOS DE BIOS ({count})",
        "bios_results_footer": "Escolha um BIOS para ver ou transferir; B/Escape: voltar",
        "bios_details": "DETALHES DO BIOS",
        "platform_field": "Plataforma: {value}",
        "status_field": "Estado: {value}",
        "required": "Obrigatório",
        "optional": "Opcional",
        "required_short": "O",
        "optional_short": "P",
        "all_regions": "todas",
        "destination_field": "Destino: {value}",
        "bios_state_valid": "válido",
        "bios_state_missing": "em falta",
        "bios_state_invalid": "inválido",
        "bios_entry_not_downloadable": (
            "O RetroBIOS tem metadados, mas não um ficheiro transferível para esta entrada."
        ),
        "bios_check_unavailable": "VERIFICAÇÃO DE BIOS INDISPONÍVEL",
        "bios_check_unavailable_message": (
            "O jogo foi instalado, mas não foi possível carregar os metadados RetroBIOS:\n"
            "{error}\nPode tentar novamente em Pesquisar e transferir BIOS."
        ),
        "required_bios_not_found": "BIOS OBRIGATÓRIO NÃO ENCONTRADO",
        "required_bios_missing_message": (
            "O arquivo do jogo não forneceu estes ficheiros BIOS obrigatórios e não foi "
            "encontrada uma cópia válida em nenhum cartão de memória:"
        ),
        "and_more": "...e mais {count}",
        "download_required_bios": "TRANSFERIR OS BIOS OBRIGATÓRIOS?",
        "download_from_retrobios": "Transferir do RetroBIOS",
        "keep_without_bios": "Manter o jogo sem BIOS",
        "firmware_warning": "O jogo poderá não iniciar sem o firmware obrigatório",
        "bios_not_downloadable": "BIOS NÃO TRANSFERÍVEL",
        "bios_not_downloadable_message": (
            "O RetroBIOS tem metadados dos requisitos, mas não uma cópia transferível dos "
            "ficheiros selecionados."
        ),
        "confirm_retrobios_download": "CONFIRMAR TRANSFERÊNCIA RETROBIOS",
        "download_verified_bios": "Transferir {count} ficheiro(s) BIOS verificados",
        "bios_legal_footer": (
            "Continue apenas se tiver autorização para obter estas cópias de segurança pessoais"
        ),
        "bios_download_cancelled": "TRANSFERÊNCIA DE BIOS CANCELADA",
        "no_incomplete_bios_installed": "Nenhum ficheiro BIOS incompleto foi instalado.",
        "bios_installed": "BIOS INSTALADO",
        "bios_installed_message": (
            "Instalados e verificados {count} ficheiro(s) BIOS em {destination}."
        ),
        "minerva_settings_title": "DEFINIÇÕES BITTORRENT DO MINERVA",
        "minerva_udp_protocol_id": "ID do protocolo UDP",
        "minerva_block_size": "Tamanho do bloco (bytes)",
        "minerva_max_torrent_bytes": "Máx. metadados torrent (bytes)",
        "minerva_max_tracker_bytes": "Máx. resposta do tracker (bytes)",
        "minerva_max_peer_attempts": "Máx. tentativas de pares",
        "minerva_peer_race_workers": "Pesquisas de pares em paralelo",
        "minerva_max_peer_timeout": "Tempo limite máx. do par (segundos)",
        "minerva_max_tracker_queries": "Máx. consultas ao tracker",
        "minerva_max_discovered_peers": "Máx. pares descobertos",
        "reset_all_defaults": "Repor todos os valores predefinidos",
        "minerva_settings_footer": "Os valores avançados são guardados localmente",
        "reset_minerva_settings": "REPOR AS DEFINIÇÕES DO MINERVA?",
        "keep_current_values": "Não - manter os valores atuais",
        "restore_defaults": "Sim - restaurar valores predefinidos",
        "reset_minerva_footer": "Isto altera os nove valores BitTorrent",
        "current_value": "Atual: {value}",
        "invalid_setting": "Valor inválido para {setting}: {error}",
        "minerva_settings_saved": "DEFINIÇÕES DO MINERVA GUARDADAS",
        "minerva_settings_saved_message": (
            "Os novos valores serão usados na próxima transferência do Minerva."
        ),
        "checking_for_update": "A PROCURAR ATUALIZAÇÃO",
        "checking_for_update_message": (
            "Instalada: v{version}\nA ler a versão mais recente do GitHub..."
        ),
        "already_up_to_date": "JÁ ESTÁ ATUALIZADO",
        "latest_release_message": "v{version} é a versão {target} publicada mais recente.",
        "application_update_available": "ATUALIZAÇÃO DA APLICAÇÃO DISPONÍVEL",
        "download_install_version": "Transferir e instalar v{version}",
        "later": "Mais tarde",
        "installed_published": "Instalada: v{installed}   Publicada: {published}",
        "installed_application_unchanged": "A aplicação instalada não foi alterada.",
        "update_ready": "ATUALIZAÇÃO PRONTA",
        "update_ready_message": (
            "v{version} será instalada agora.\n"
            "Volte a abrir o Pocket Harbor em Ferramentas após este ecrã fechar."
        ),
        "connecting_github": "A ligar ao GitHub...",
        "cancelling_update": "A CANCELAR ATUALIZAÇÃO",
        "cancelling_update_message": (
            "A remover a atualização incompleta; a versão instalada não será alterada..."
        ),
        "exit_pocket_harbor": "SAIR DO POCKET HARBOR?",
        "return_to_pocket_harbor": "Não - voltar ao Pocket Harbor",
        "confirm_exit": "Sim - sair",
        "exit_footer": "Confirme antes de voltar ao EmulationStation",
        "card_number": "CARTÃO {index}",
        "choose_library_location": "Escolha onde a biblioteca de jogos está guardada",
        "downloading": "A TRANSFERIR",
        "downloaded_kib": "{label}\n{kib} KiB transferidos",
        "cancel_download_footer": "B/Escape: cancelar transferência",
        "connecting_download_service": "A ligar ao serviço de transferência...",
        "cancelling_download": "A CANCELAR TRANSFERÊNCIA",
        "cancelling_download_message": (
            "A fechar ligações de rede e a remover ficheiros parciais..."
        ),
        "minerva_torrent_changed": "O TORRENT DO MINERVA MUDOU",
        "minerva_torrent_changed_message": (
            "Ficheiro do catálogo:\n{filename}\nPosição no catálogo: #{index}\n\nO torrent "
            "contém agora {count} ficheiros e já não tem uma correspondência inequívoca. "
            "Reveja os candidatos mais próximos ou cancele; nenhum jogo foi instalado."
        ),
        "minerva_candidate": (
            "#{index}  {filename}  | {size} | {score}% de correspondência | {path}"
        ),
        "choose_minerva_torrent_file": "ESCOLHER FICHEIRO TORRENT DO MINERVA",
        "minerva_candidates_footer": "Candidatos seguros mais próximos; B/Escape: cancelar",
        "review_minerva_file": "REVER FICHEIRO DO MINERVA",
        "review_minerva_file_message": (
            "Esperado pelo catálogo:\n{expected}\n\nFicheiro torrent selecionado:\n{selected}\n"
            "Posição no torrent: #{index}\nTamanho: {size}\nSemelhança do título: {score}%"
        ),
        "confirm_minerva_file": "CONFIRMAR FICHEIRO DO MINERVA",
        "cancel_download": "Cancelar transferência",
        "download_filename": "Transferir {filename}",
        "confirm_minerva_file_footer": "Só será transferido o ficheiro torrent selecionado",
        "not_detected": "não detetado",
        "not_configured": "não configurado",
        "status_title": "ESTADO DO POCKET HARBOR",
        "status_message": (
            "Loja predefinida: {store}\nLojas: {stores}\nÁrea temporária: {staging}\n"
            "Raiz das ROM: {roms}\nPlataformas: {platforms}\nHardware: {hardware}\n"
            "Compatível: {compatible}\nEcrã: {resolution} píxeis; {width}x{height} células "
            "de terminal\nEntradas DT: {inputs} ({keys} teclas GPIO)\nComando: {controller} "
            "(entrada nativa Linux)\n\nControlos\nDirecional / analógicos / setas   Mover "
            "seleção\nA / Enter        Selecionar\nB / Escape       Voltar\n"
            "X                Confirmar texto da pesquisa\n\nO texto pode ser introduzido com "
            "o teclado integrado no ecrã."
        ),
        "keyboard_letters": "LETRAS",
        "keyboard_symbols": "SÍMBOLOS",
        "keyboard_accents": "ACENTOS",
        "operation_failed": "A operação falhou.\nDetalhes técnicos: {error}",
        "terminal_too_small": "O terminal deve ter pelo menos 40 colunas e 15 linhas.",
    },
}

for _language_code, _messages in _TUI_FLOW_TRANSLATIONS.items():
    _TRANSLATIONS[_language_code].update(_messages)


def normalize_language(value: object) -> LanguageCode:
    """Return a supported language code, defaulting safely to English."""

    if isinstance(value, str):
        normalized = value.strip().casefold().split("-", maxsplit=1)[0]
        if normalized in {language.code for language in LANGUAGES}:
            return normalized
    return DEFAULT_LANGUAGE


def language_name(code: LanguageCode) -> str:
    """Return the native display name for a supported language."""

    return next(language.name for language in LANGUAGES if language.code == code)


def translate(code: LanguageCode, key: str, **values: object) -> str:
    """Translate a stable UI key with English fallback and named interpolation."""

    template = _TRANSLATIONS.get(code, _ENGLISH).get(key)
    if template is None:
        template = _ENGLISH[key]
    return template.format_map(values) if values else template


def missing_translation_keys(language: LanguageCode) -> frozenset[str]:
    """Expose catalogue completeness for validation tests."""

    return frozenset(_ENGLISH).difference(_TRANSLATIONS[language])


def mismatched_placeholder_keys(language: LanguageCode) -> frozenset[str]:
    """Return translations whose named format fields differ from English."""

    formatter = Formatter()

    def fields(template: str) -> frozenset[str]:
        return frozenset(
            field_name
            for _literal, field_name, _format_spec, _conversion in formatter.parse(template)
            if field_name is not None
        )

    catalogue = _TRANSLATIONS[language]
    return frozenset(
        key
        for key, english in _ENGLISH.items()
        if key in catalogue and fields(catalogue[key]) != fields(english)
    )
