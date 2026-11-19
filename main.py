import inspect
import json
import math
import os
import re
import sys
import tempfile
import time
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable


DATABASE_FILE = "lab10_database.json"
MAX_RECORDS = 200
MAX_COMMAND_LENGTH = 1000

DICTIONARY = {
    "groups": {
        "A": "Початковий рівень",
        "B": "Середній рівень",
        "C": "Просунутий рівень",
        "TEAM": "Робоча добірка",
        "CHECK": "На перевірці",
        "NEW": "Нові записи",
    },
    "fields": {
        "id": "Ідентифікатор",
        "group": "Група",
        "a": "Оцінка першого критерію",
        "b": "Оцінка другого критерію",
        "s": "Зважений бал",
    },
}

COMMAND_MESSAGES = {
    "ДАНІ": "Некоректні дані команди.",
    "ДУБЛЬ": "Запис із таким ідентифікатором уже існує.",
    "НЕМАЄ": "Запис із таким ідентифікатором відсутній.",
    "МЕЖІ": "Порушено допустимі межі запису або реєстру.",
}

_GROUP_PATTERN = re.compile(r"[A-Z][A-Z0-9_]{0,7}\Z")


@dataclass
class Record:
    id: int
    group: str
    a: int
    b: int


class Registry:
    def __init__(self, records: list[Record]) -> None:
        if not isinstance(records, list) or len(records) > MAX_RECORDS:
            raise ValueError("ДАНІ")

        copied_records: list[Record] = []
        used_ids: set[int] = set()

        for record in records:
            if not _valid_record(record) or record.id in used_ids:
                raise ValueError("ДАНІ")
            used_ids.add(record.id)
            copied_records.append(
                Record(record.id, record.group, record.a, record.b)
            )

        self.records = copied_records

    def snapshot(self) -> list[Record]:
        return [
            Record(record.id, record.group, record.a, record.b)
            for record in self.records
        ]


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _valid_group(group: Any) -> bool:
    return isinstance(group, str) and _GROUP_PATTERN.fullmatch(group) is not None


def _valid_record(record: Any) -> bool:
    return (
        isinstance(record, Record)
        and _is_integer(record.id)
        and 1 <= record.id <= 9999
        and _valid_group(record.group)
        and _is_integer(record.a)
        and 0 <= record.a <= 100
        and _is_integer(record.b)
        and 0 <= record.b <= 100
    )


def _record_from_dict(data: Any) -> Record:
    if not isinstance(data, dict) or set(data) != {"id", "group", "a", "b"}:
        raise ValueError("ДАНІ")

    record = Record(data["id"], data["group"], data["a"], data["b"])
    if not _valid_record(record):
        raise ValueError("ДАНІ")
    return record


def _reject_json_constant(value: str) -> None:
    raise json.JSONDecodeError("Недопустима JSON-константа", value, 0)


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("ДАНІ")
        result[key] = value
    return result


def load_registry(path: str) -> Registry:
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(
            file,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_unique_json_object,
        )

    if not isinstance(data, list) or len(data) > MAX_RECORDS:
        raise ValueError("ДАНІ")

    records = [_record_from_dict(item) for item in data]
    return Registry(records)


def save_registry(registry: Registry, path: str) -> None:
    records = registry.snapshot()
    Registry(records)
    records.sort(key=lambda record: record.id)

    data = [
        {
            "id": record.id,
            "group": record.group,
            "a": record.a,
            "b": record.b,
        }
        for record in records
    ]

    directory = os.path.dirname(os.path.abspath(path))
    temporary_path: str | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=".lab10_database_",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary_path = file.name
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())

        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                os.remove(temporary_path)
            except FileNotFoundError:
                pass


def linear_search(records: list[Record], q: int) -> Record | None:
    for record in records:
        if record.id == q:
            return record
    return None


def binary_search(records: list[Record], q: int) -> Record | None:
    left = 0
    right = len(records) - 1

    while left <= right:
        middle = (left + right) // 2
        current_id = records[middle].id

        if current_id == q:
            return records[middle]
        if current_id < q:
            left = middle + 1
        else:
            right = middle - 1

    return None


def _weighted_score(record: Record) -> int:
    return (record.a * 40 + record.b * 60) // 100


def _display_group(code: str, dictionary: dict) -> str:
    group_name = dictionary.get("groups", {}).get(code)
    if group_name is None:
        return code
    return f"{code} ({group_name})"


def analyze(
    registry: Registry,
    group: str,
    threshold: int,
    search_id: int,
    dictionary: dict,
) -> list[str]:
    """Аналіз реєстру."""
    linear_result = linear_search(registry.records, search_id)
    ordered_by_id = sorted(registry.records, key=lambda record: record.id)
    binary_result = binary_search(ordered_by_id, search_id)

    if linear_result is not binary_result:
        raise RuntimeError("Результати лінійного й бінарного пошуку не збігаються")

    fields = dictionary["fields"]
    result_lines: list[str] = []

    if linear_result is None:
        result_lines.append("Запис із заданим ідентифікатором не знайдено.")
    else:
        found = linear_result
        result_lines.append(
            f"Знайдений запис. {fields['id']} - {found.id}. "
            f"{fields['group']} - {_display_group(found.group, dictionary)}. "
            f"{fields['a']} - {found.a}. {fields['b']} - {found.b}. "
            f"{fields['s']} - {_weighted_score(found)}."
        )

    selected = [
        record
        for record in registry.records
        if (group == "*" or record.group == group) and record.b >= threshold
    ]
    selected.sort(
        key=lambda record: (
            _weighted_score(record),
            record.group,
            record.id,
        )
    )

    if not selected:
        result_lines.extend(
            [
                "За умовою відбору записів немає.",
                "Сума показників відібраних записів - 0.",
                "Підсумків за групами немає.",
            ]
        )
        return result_lines

    result_lines.append(
        "Відібрані записи - "
        + ", ".join(f"No{record.id}" for record in selected)
        + "."
    )

    scores = [_weighted_score(record) for record in selected]
    result_lines.append(f"Сума показників «{fields['s']}» - {sum(scores)}.")

    group_totals: dict[str, list[int]] = {}
    for record, score in zip(selected, scores):
        totals = group_totals.get(record.group)
        if totals is None:
            group_totals[record.group] = [1, score, score]
        else:
            totals[0] += 1
            totals[1] += score
            if score > totals[2]:
                totals[2] = score

    for code in sorted(group_totals):
        count, subtotal, maximum = group_totals[code]
        result_lines.append(
            f"Група {_display_group(code, dictionary)}. Записів - {count}. "
            f"Сума показників - {subtotal}. Найбільший показник - {maximum}."
        )

    return result_lines


def _find_position(records: list[Record], record_id: int) -> int:
    for index, record in enumerate(records):
        if record.id == record_id:
            return index
    return -1


def _validate_command_keys(command: dict, expected: set[str]) -> None:
    if set(command) != expected:
        raise ValueError("ДАНІ")


def _valid_command_id(value: Any) -> bool:
    return _is_integer(value) and 1 <= value <= 9999


def _valid_adjustment(value: Any) -> bool:
    return _is_integer(value) and -10000 <= value <= 10000


def _parse_command(raw: str) -> Any:
    if not isinstance(raw, str) or not 1 <= len(raw) <= MAX_COMMAND_LENGTH:
        raise ValueError("ДАНІ")

    try:
        return json.loads(
            raw,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_unique_json_object,
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        raise ValueError("ДАНІ") from None


def _apply_command_impl(registry: Registry, raw: str) -> str:
    command = _parse_command(raw)

    if not isinstance(command, dict):
        raise ValueError("ДАНІ")

    operation = command.get("op")
    if not isinstance(operation, str) or operation not in {
        "ADD", "ADJUST", "MOVE", "DELETE"
    }:
        raise ValueError("ДАНІ")

    if operation == "ADD":
        _validate_command_keys(command, {"op", "record"})
        new_record = _record_from_dict(command["record"])

        if _find_position(registry.records, new_record.id) != -1:
            raise ValueError("ДУБЛЬ")
        if len(registry.records) >= MAX_RECORDS:
            raise ValueError("МЕЖІ")

        registry.records.append(new_record)
        return "OK"

    if operation == "ADJUST":
        _validate_command_keys(command, {"op", "id", "da", "db"})
        record_id = command["id"]
        da = command["da"]
        db = command["db"]

        if (
            not _valid_command_id(record_id)
            or not _valid_adjustment(da)
            or not _valid_adjustment(db)
        ):
            raise ValueError("ДАНІ")

        position = _find_position(registry.records, record_id)
        if position == -1:
            raise ValueError("НЕМАЄ")

        record = registry.records[position]
        new_a = record.a + da
        new_b = record.b + db

        if not (0 <= new_a <= 100 and 0 <= new_b <= 100):
            raise ValueError("МЕЖІ")

        record.a = new_a
        record.b = new_b
        return "OK"

    if operation == "MOVE":
        _validate_command_keys(command, {"op", "id", "group"})
        record_id = command["id"]
        new_group = command["group"]

        if not _valid_command_id(record_id) or not _valid_group(new_group):
            raise ValueError("ДАНІ")

        position = _find_position(registry.records, record_id)
        if position == -1:
            raise ValueError("НЕМАЄ")

        registry.records[position].group = new_group
        return "OK"

    _validate_command_keys(command, {"op", "id"})
    record_id = command["id"]

    if not _valid_command_id(record_id):
        raise ValueError("ДАНІ")

    position = _find_position(registry.records, record_id)
    if position == -1:
        raise ValueError("НЕМАЄ")

    del registry.records[position]
    return "OK"


journal: list[tuple[str, bool, float]] = []


def timed(
    label: str,
    log: list,
    clock: Callable[[], float] = time.perf_counter,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(function: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(function)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            wrapper.last_result = None
            wrapper.last_exception_type = None
            wrapper.last_exception_message = None
            wrapper.last_observed = None

            try:
                started_at = clock()
            except Exception:
                started_at = None

            success = False
            try:
                result = function(*args, **kwargs)
                success = True
                wrapper.last_result = result
                wrapper.last_observed = (True, result)
                return result
            except BaseException as error:
                wrapper.last_exception_type = type(error)
                wrapper.last_exception_message = str(error)
                wrapper.last_observed = (False, (type(error), str(error)))
                raise
            finally:
                elapsed = 0.0
                if started_at is not None:
                    try:
                        measured = clock() - started_at
                        if (
                            isinstance(measured, (int, float))
                            and not isinstance(measured, bool)
                            and math.isfinite(measured)
                            and measured >= 0
                        ):
                            elapsed = float(measured)
                    except Exception:
                        elapsed = 0.0
                log.append((label, success, elapsed))

        wrapper.last_result = None
        wrapper.last_exception_type = None
        wrapper.last_exception_message = None
        wrapper.last_observed = None
        return wrapper

    return decorator


@timed("change", journal)
def apply_command(registry: Registry, raw: str) -> str:
    """Зміна реєстру."""
    return _apply_command_impl(registry, raw)


original_apply_command = apply_command.__wrapped__


def check_metadata(original: Callable[..., Any], wrapped: Callable[..., Any]) -> bool:
    try:
        return (
            getattr(wrapped, "__wrapped__", None) is original
            and original.__name__ == wrapped.__name__
            and original.__doc__ == wrapped.__doc__
            and original.__annotations__ == wrapped.__annotations__
            and inspect.signature(original) == inspect.signature(wrapped)
        )
    except (AttributeError, TypeError, ValueError):
        return False


def _state_signature(registry: Registry) -> tuple[tuple[int, str, int, int], ...]:
    return tuple(
        sorted(
            (record.id, record.group, record.a, record.b)
            for record in registry.records
        )
    )


def check_call(
    original: Callable[..., Any],
    wrapped: Callable[..., Any],
    before: Registry,
    after: Registry,
    args: tuple,
    observed: tuple,
) -> bool:
    if not check_metadata(original, wrapped):
        return False

    try:
        comparison_registry = Registry(before.snapshot())
        try:
            result = original(comparison_registry, *args)
            expected = (True, result)
        except BaseException as error:
            expected = (False, (type(error), str(error)))

        return (
            expected == observed
            and _state_signature(comparison_registry) == _state_signature(after)
        )
    except (AttributeError, TypeError, ValueError):
        return False


def _read_commands(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8", newline="") as file:
        content = file.read()

    if not content:
        return []

    lines = content.split("\n")
    if lines and lines[-1] == "":
        lines.pop()

    commands: list[str] = []
    for line in lines:
        if line.endswith("\r"):
            line = line[:-1]
        if line != "":
            commands.append(line)

    return commands


def _count_valid_journal_entries(expected_successes: list[bool]) -> int:
    valid_count = 0

    for index, entry in enumerate(journal):
        if not isinstance(entry, tuple) or len(entry) != 3:
            continue

        label, success, elapsed = entry
        if label != "change" or not isinstance(success, bool):
            continue
        if index >= len(expected_successes) or success is not expected_successes[index]:
            continue
        if not isinstance(elapsed, (int, float)) or isinstance(elapsed, bool):
            continue
        if elapsed < 0:
            continue
        if isinstance(elapsed, float) and not math.isfinite(elapsed):
            continue

        valid_count += 1

    return valid_count


def main() -> None:
    journal.clear()

    input_lines = [sys.stdin.readline().rstrip("\r\n") for _ in range(4)]
    operations_filename = input_lines[0]
    selected_group = input_lines[1]
    threshold = int(input_lines[2])
    search_id = int(input_lines[3])

    try:
        registry = load_registry(DATABASE_FILE)
    except FileNotFoundError:
        print("Помилка. Файл бази відсутній.")
        return
    except json.JSONDecodeError:
        print("Помилка. Файл бази містить некоректний JSON.")
        return
    except (ValueError, UnicodeDecodeError):
        print("Помилка. База містить недопустиму структуру або записи.")
        return

    commands = _read_commands(operations_filename)
    command_messages: list[str] = []
    expected_successes: list[bool] = []
    all_checks_passed = True

    for number, raw in enumerate(commands, start=1):
        before = Registry(registry.snapshot())

        try:
            result = apply_command(registry, raw)
            observed = (True, result)
            expected_successes.append(True)
            command_messages.append(f"Команда {number} - виконано.")
        except ValueError as error:
            observed = apply_command.last_observed
            expected_successes.append(False)
            reason = COMMAND_MESSAGES.get(str(error), COMMAND_MESSAGES["ДАНІ"])
            command_messages.append(f"Команда {number} - відхилено. {reason}")

        after = Registry(registry.snapshot())
        if not check_call(
            original_apply_command,
            apply_command,
            before,
            after,
            (raw,),
            observed,
        ):
            all_checks_passed = False

    if not commands:
        all_checks_passed = check_metadata(original_apply_command, apply_command)

    result_lines = [f"У реєстрі записів - {len(registry.records)}."]
    result_lines.extend(
        analyze(registry, selected_group, threshold, search_id, DICTIONARY)
    )

    save_registry(registry, DATABASE_FILE)

    calls = len(commands)
    valid_entries = _count_valid_journal_entries(expected_successes)

    if calls:
        conclusion = (
            "Метадані й поведінку збережено."
            if all_checks_passed
            else "Метадані або поведінка змінилися."
        )
    else:
        conclusion = (
            "Метадані збережено."
            if all_checks_passed
            else "Метадані змінилися."
        )

    result_lines.append(
        f"Перевірка декоратора. Викликів - {calls}. "
        f"Коректних записів журналу - {valid_entries}. {conclusion}"
    )

    for message in command_messages:
        print(message)
    for line in result_lines:
        print(line)


if __name__ == "__main__":
    main()
