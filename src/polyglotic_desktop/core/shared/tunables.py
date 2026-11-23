"""Typed product defaults. Resolution is pure; installing swaps one complete snapshot."""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import cast

type Value = int | float | str | tuple[float, ...]


class Applies(StrEnum):
    LIVE = "live"
    NEW_WINDOWS = "new windows"
    RESTART = "restart"


@dataclass(frozen=True, slots=True)
class Tunable[T: Value]:
    name: str
    default: T
    unit: str
    bounds: tuple[float, float] | tuple[str, ...]
    source: str
    applies: Applies

    @property
    def value(self) -> T:
        return cast(T, _active.values.get(self.name, self.default))

    @property
    def configured(self) -> T:
        """Default before learner choices, for preset reset and change tracking."""
        return cast(T, _active.defaults.get(self.name, self.default))

    def checked(self, raw: object) -> Value:
        if isinstance(self.default, str):
            if not isinstance(raw, str) or raw not in self.bounds:
                raise ValueError("expected one of " + ", ".join(map(str, self.bounds)))
            return raw
        low, high = cast(tuple[float, float], self.bounds)

        def number(n: object) -> float:
            if isinstance(n, bool) or not isinstance(n, (int, float)):
                raise TypeError("expected a number")
            if not low <= n <= high:
                raise ValueError(f"outside {low:g}..{high:g} {self.unit}")
            return float(n)

        if isinstance(self.default, tuple):
            if not isinstance(raw, (list, tuple)) or not raw:
                raise ValueError("expected a non-empty list of numbers")
            return tuple(number(n) for n in raw)
        if isinstance(self.default, int):
            if isinstance(raw, bool) or not isinstance(raw, int):
                raise TypeError("expected a whole number")
            number(raw)
            return raw
        return number(raw)


_by_name: dict[str, Tunable[Value]] = {}


def tunable[T: Value](
    name: str,
    default: T,
    unit: str,
    bounds: tuple[float, float] | tuple[str, ...],
    *,
    source: str,
    applies: Applies = Applies.LIVE,
) -> Tunable[T]:
    if name in _by_name:
        raise ValueError(f"duplicate tunable {name}")
    declaration = Tunable(name, default, unit, bounds, source, applies)
    declaration.checked(default)
    _by_name[name] = declaration
    return declaration


def declarations() -> Mapping[str, Tunable[Value]]:
    return _by_name.copy()


type Layer = tuple[str, Mapping[str, object]]
type Rule = Callable[[Mapping[str, Value], Mapping[str, Value]], str | None]


@dataclass(frozen=True, slots=True)
class Resolution:
    values: Mapping[str, Value]
    warnings: tuple[str, ...]
    defaults: Mapping[str, Value]
    refused_choices: Mapping[str, object]


_active = Resolution({}, (), {}, {})


def refused_choices() -> Mapping[str, object]:
    return _active.refused_choices


def resolve(layers: Iterable[Layer], rules: Iterable[Rule]) -> Resolution:
    """Unknown names and invalid fields are skipped. A broken rule rejects the layer."""
    values = {name: item.default for name, item in _by_name.items()}
    defaults = values
    refused: dict[str, object] = {}
    warnings: list[str] = []
    checks = tuple(rules)
    for rule in checks:
        if reason := rule(values, {}):
            raise ValueError(f"invalid shipped tunables: {reason}")
    for label, layer in layers:
        updates: dict[str, Value] = {}
        for name, raw in layer.items():
            item = _by_name.get(name)
            if item is None:
                warnings.append(f"{label}: unknown tunable {name}, ignored")
                continue
            try:
                updates[name] = item.checked(raw)
            except (TypeError, ValueError) as error:
                if label == "learner":
                    refused[name] = raw
                warnings.append(f"{label}: {name} refused: {error} ({item.source})")
        if not updates:
            continue
        candidate = values | updates
        for rule in checks:
            if reason := rule(candidate, updates):
                if label == "learner":
                    refused.update(layer)
                warnings.append(f"{label}: whole layer refused: {reason}")
                break
        else:
            values = candidate
            if label != "learner":
                defaults = values
    return Resolution(
        MappingProxyType(values),
        tuple(warnings),
        MappingProxyType(defaults),
        MappingProxyType(refused),
    )


def install(resolved: Resolution) -> None:
    global _active
    _active = resolved
