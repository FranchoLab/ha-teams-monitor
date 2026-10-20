"""Read public macOS power assertions without parsing command output."""

import ctypes
import plistlib
from dataclasses import dataclass
from pathlib import Path

_IOKIT_PATH = "/System/Library/Frameworks/IOKit.framework/IOKit"
_CORE_FOUNDATION_PATH = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
_LIBPROC_PATH = "/usr/lib/libproc.dylib"
_PROCESS_ALL_PIDS = 1
_CF_NUMBER_SINT32_TYPE = 3
_CF_STRING_ENCODING_UTF8 = 0x08000100
_TEAMS_PROCESS_NAME = "msteams"


class PowerAssertionReadError(Exception):
    """Raised when macOS power assertion data cannot be read safely."""


@dataclass(frozen=True, slots=True)
class TeamsPowerAssertions:
    process_found: bool
    version: str | None
    assertion_types: frozenset[str]


def _bundle_version(executable_path: str) -> str | None:
    for bundle_path in Path(executable_path).parents:
        if bundle_path.suffix.casefold() != ".app":
            continue
        info_path = bundle_path / "Contents" / "Info.plist"
        try:
            with info_path.open("rb") as info_file:
                info = plistlib.load(info_file)
        except (OSError, plistlib.InvalidFileException):
            return None
        if not isinstance(info, dict):
            return None
        version = info.get("CFBundleVersion")
        return version if isinstance(version, str) else None
    return None


class IOKitPowerAssertionSource:
    """Read assertion types for the running MSTeams process via public APIs."""

    def read(self) -> TeamsPowerAssertions:
        try:
            iokit = ctypes.CDLL(_IOKIT_PATH)
            core_foundation = ctypes.CDLL(_CORE_FOUNDATION_PATH)
            libproc = ctypes.CDLL(_LIBPROC_PATH)
            teams_processes = self._teams_processes(libproc)
            if not teams_processes:
                return TeamsPowerAssertions(False, None, frozenset())
            version = self._single_version(teams_processes)
            assertion_types = self._assertions_for_processes(
                iokit,
                core_foundation,
                {process_id for process_id, _ in teams_processes},
            )
        except PowerAssertionReadError:
            raise
        except AttributeError as error:
            raise PowerAssertionReadError("Required macOS API symbol is unavailable.") from error
        except OSError as error:
            raise PowerAssertionReadError(
                f"macOS API call failed with errno {error.errno}."
            ) from error
        except ValueError as error:
            raise PowerAssertionReadError("macOS API returned invalid data.") from error
        return TeamsPowerAssertions(True, version, assertion_types)

    @staticmethod
    def _teams_processes(libproc: ctypes.CDLL) -> list[tuple[int, str | None]]:
        proc_listpids = libproc.proc_listpids
        proc_listpids.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_int]
        proc_listpids.restype = ctypes.c_int
        required_bytes = proc_listpids(_PROCESS_ALL_PIDS, 0, None, 0)
        if required_bytes <= 0:
            raise PowerAssertionReadError("Unable to enumerate macOS processes.")

        capacity = required_bytes // ctypes.sizeof(ctypes.c_int32) + 16
        process_ids = (ctypes.c_int32 * capacity)()
        returned_bytes = proc_listpids(
            _PROCESS_ALL_PIDS,
            0,
            ctypes.cast(process_ids, ctypes.c_void_p),
            ctypes.sizeof(process_ids),
        )
        if returned_bytes < 0:
            raise PowerAssertionReadError("Unable to enumerate macOS processes.")

        proc_name = libproc.proc_name
        proc_name.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        proc_name.restype = ctypes.c_int
        proc_pidpath = libproc.proc_pidpath
        proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        proc_pidpath.restype = ctypes.c_int

        teams_processes = []
        process_count = returned_bytes // ctypes.sizeof(ctypes.c_int32)
        for process_id in process_ids[:process_count]:
            if process_id <= 0:
                continue
            name_buffer = ctypes.create_string_buffer(64)
            if proc_name(process_id, name_buffer, len(name_buffer)) <= 0:
                continue
            if (
                name_buffer.value.decode("utf-8", errors="replace").casefold()
                != _TEAMS_PROCESS_NAME
            ):
                continue
            path_buffer = ctypes.create_string_buffer(4096)
            path_length = proc_pidpath(process_id, path_buffer, len(path_buffer))
            executable_path = path_buffer.value.decode("utf-8", errors="replace")
            version = _bundle_version(executable_path) if path_length > 0 else None
            teams_processes.append((process_id, version))
        return teams_processes

    @staticmethod
    def _single_version(teams_processes: list[tuple[int, str | None]]) -> str | None:
        versions = {version for _, version in teams_processes}
        if len(versions) != 1 or None in versions:
            return None
        return next(iter(versions))

    @staticmethod
    def _assertions_for_processes(
        iokit: ctypes.CDLL,
        core_foundation: ctypes.CDLL,
        process_ids: set[int],
    ) -> frozenset[str]:
        copy_assertions = iokit.IOPMCopyAssertionsByProcess
        copy_assertions.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
        copy_assertions.restype = ctypes.c_int
        assertions_by_pid = ctypes.c_void_p()
        if copy_assertions(ctypes.byref(assertions_by_pid)) != 0 or not assertions_by_pid.value:
            raise PowerAssertionReadError("Unable to query macOS power assertions.")

        dictionary_get_count = core_foundation.CFDictionaryGetCount
        dictionary_get_count.argtypes = [ctypes.c_void_p]
        dictionary_get_count.restype = ctypes.c_long
        dictionary_get_keys_and_values = core_foundation.CFDictionaryGetKeysAndValues
        dictionary_get_keys_and_values.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        dictionary_get_value = core_foundation.CFDictionaryGetValue
        dictionary_get_value.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        dictionary_get_value.restype = ctypes.c_void_p
        number_get_value = core_foundation.CFNumberGetValue
        number_get_value.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        number_get_value.restype = ctypes.c_bool
        array_get_count = core_foundation.CFArrayGetCount
        array_get_count.argtypes = [ctypes.c_void_p]
        array_get_count.restype = ctypes.c_long
        array_get_value = core_foundation.CFArrayGetValueAtIndex
        array_get_value.argtypes = [ctypes.c_void_p, ctypes.c_long]
        array_get_value.restype = ctypes.c_void_p
        string_get_c_string = core_foundation.CFStringGetCString
        string_get_c_string.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_long,
            ctypes.c_uint32,
        ]
        string_get_c_string.restype = ctypes.c_bool
        release = core_foundation.CFRelease
        release.argtypes = [ctypes.c_void_p]
        create_string = core_foundation.CFStringCreateWithCString
        create_string.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
        create_string.restype = ctypes.c_void_p
        assertion_type_key = create_string(None, b"AssertType", _CF_STRING_ENCODING_UTF8)

        try:
            if not assertion_type_key:
                raise PowerAssertionReadError("Unable to create the IOKit assertion type key.")
            count = dictionary_get_count(assertions_by_pid)
            keys = (ctypes.c_void_p * count)()
            values = (ctypes.c_void_p * count)()
            dictionary_get_keys_and_values(assertions_by_pid, keys, values)
            assertion_types = set()
            for index in range(count):
                process_id = ctypes.c_int32()
                if not number_get_value(
                    keys[index], _CF_NUMBER_SINT32_TYPE, ctypes.byref(process_id)
                ):
                    raise PowerAssertionReadError("Unable to read an assertion process identifier.")
                if process_id.value not in process_ids:
                    continue
                assertions = values[index]
                assertion_count = array_get_count(assertions)
                for assertion_index in range(assertion_count):
                    assertion = array_get_value(assertions, assertion_index)
                    assertion_type = dictionary_get_value(assertion, assertion_type_key)
                    if not assertion_type:
                        raise PowerAssertionReadError("Unable to read an assertion type.")
                    buffer = ctypes.create_string_buffer(512)
                    if not string_get_c_string(
                        assertion_type,
                        buffer,
                        len(buffer),
                        _CF_STRING_ENCODING_UTF8,
                    ):
                        raise PowerAssertionReadError("Unable to decode an assertion type.")
                    assertion_types.add(buffer.value.decode("utf-8"))
            return frozenset(assertion_types)
        finally:
            if assertion_type_key:
                release(assertion_type_key)
            release(assertions_by_pid)
