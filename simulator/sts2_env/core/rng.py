"""Deterministic RNG matching the game's seeded RNG wrapper."""

from __future__ import annotations

import math


INT_MAX = 2_147_483_647
INT_MIN = -2_147_483_648
INT_MAX_EXCLUSIVE = INT_MAX + 1
UINT_MASK = 0xFFFFFFFF


def _to_int32(value: int) -> int:
    value &= UINT_MASK
    if value >= 0x80000000:
        value -= 0x100000000
    return value


def _to_uint32(value: int) -> int:
    return value & UINT_MASK


def deterministic_hash_code(text: str) -> int:
    """Match StringHelper.GetDeterministicHashCode from the game."""
    num = 352654597
    num2 = num
    for index in range(0, len(text), 2):
        num = _to_int32(_to_int32(num << 5) + num)
        num = _to_int32(num ^ ord(text[index]))
        if index == len(text) - 1:
            break
        num2 = _to_int32(_to_int32(num2 << 5) + num2)
        num2 = _to_int32(num2 ^ ord(text[index + 1]))
    return _to_int32(num + _to_int32(num2 * 1_566_083_941))


class _DotNetCompatRandom:
    """System.Random seeded implementation used by .NET for Random(int)."""

    def __init__(self, seed: int):
        self._seed_array = [0] * 56
        self._inext = 0
        self._inextp = 21
        self._initialize(seed)

    def _initialize(self, seed: int) -> None:
        subtraction = INT_MAX if seed == INT_MIN else abs(seed)
        mj = _to_int32(161_803_398 - subtraction)
        self._seed_array[55] = mj
        mk = 1
        ii = 0
        for i in range(1, 55):
            ii += 21
            if ii >= 55:
                ii -= 55
            self._seed_array[ii] = mk
            mk = _to_int32(mj - mk)
            if mk < 0:
                mk += INT_MAX
            mj = self._seed_array[ii]
        for _ in range(1, 5):
            for i in range(1, 56):
                n = i + 30
                if n >= 55:
                    n -= 55
                self._seed_array[i] = _to_int32(self._seed_array[i] - self._seed_array[1 + n])
                if self._seed_array[i] < 0:
                    self._seed_array[i] += INT_MAX

    def internal_sample(self) -> int:
        loc_inext = self._inext + 1
        if loc_inext >= 56:
            loc_inext = 1
        loc_inextp = self._inextp + 1
        if loc_inextp >= 56:
            loc_inextp = 1

        ret = _to_int32(self._seed_array[loc_inext] - self._seed_array[loc_inextp])
        if ret == INT_MAX:
            ret -= 1
        if ret < 0:
            ret += INT_MAX
        self._seed_array[loc_inext] = ret
        self._inext = loc_inext
        self._inextp = loc_inextp
        return ret

    def sample(self) -> float:
        return self.internal_sample() * (1.0 / INT_MAX)

    def get_sample_for_large_range(self) -> float:
        result = self.internal_sample()
        if self.internal_sample() % 2 == 0:
            result = -result
        value = result + (INT_MAX - 1)
        return value / (2 * INT_MAX - 1)


class Rng:
    """Seeded random number generator compatible with the game's Rng class.

    The public ``next_int(low, high)`` API keeps this project's inclusive
    upper bound convention, while the underlying sequence uses C#'s seeded
    ``System.Random`` implementation.
    """

    def __init__(self, seed: int = 0, name: str | None = None, counter: int = 0):
        self._base_seed = _to_uint32(seed)
        if name is None:
            self._seed = self._base_seed
        else:
            self._seed = _to_uint32(self._base_seed + _to_uint32(deterministic_hash_code(name)))
        self._rng = _DotNetCompatRandom(_to_int32(self._seed))
        self._counter = 0
        self.fast_forward_counter(counter)

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def counter(self) -> int:
        return self._counter

    def fast_forward_counter(self, target_count: int) -> None:
        if self._counter > target_count:
            raise ValueError(
                f"Cannot fast-forward an Rng counter to a lower number "
                f"(current = {self._counter}, target = {target_count})"
            )
        while self._counter < target_count:
            self._counter += 1
            self._rng.internal_sample()

    def next_int(self, low: int, high: int) -> int:
        """Return random int in [low, high] inclusive."""
        if low > high:
            raise ValueError("low must be <= high")
        self._counter += 1
        exclusive_high = high + 1
        range_size = exclusive_high - low
        if range_size <= INT_MAX:
            return int(self._rng.sample() * range_size) + low
        return int(self._rng.get_sample_for_large_range() * range_size) + low

    def next_int_exclusive(self, low: int, high: int) -> int:
        """Return random int in [low, high), matching C# Random.Next(min, max)."""
        if low >= high:
            raise ValueError("low must be < high")
        return self.next_int(low, high - 1)

    def next_bool(self) -> bool:
        """Return random bool matching the game's Rng.NextBool."""
        return self.next_int(0, 1) == 0

    def random_int(self, low: int, high: int) -> int:
        """Backward-compatible alias for ``next_int``."""
        return self.next_int(low, high)

    def next_float(self, upper: float = 1.0) -> float:
        """Return random float in [0, upper)."""
        self._counter += 1
        return self._rng.sample() * upper

    def shuffle(self, lst: list) -> None:
        """In-place shuffle."""
        for index in range(len(lst) - 1, 0, -1):
            swap_index = self.next_int(0, index)
            lst[index], lst[swap_index] = lst[swap_index], lst[index]

    def choice(self, lst: list):
        """Pick a random element."""
        if not lst:
            raise IndexError("Cannot choose from an empty list")
        return lst[self.next_int(0, len(lst) - 1)]

    def sample(self, lst: list, k: int) -> list:
        """Pick k distinct elements."""
        if k < 0 or k > len(lst):
            raise ValueError("Sample larger than population or is negative")
        pool = list(lst)
        result = []
        for _ in range(k):
            index = self.next_int(0, len(pool) - 1)
            result.append(pool.pop(index))
        return result

    def next_float_range(self, low: float, high: float) -> float:
        """Return random float in [low, high)."""
        if low > high:
            raise ValueError("low must be <= high")
        self._counter += 1
        return low + self._rng.sample() * (high - low)

    def next_gaussian_int(self, mean: float, stddev: float, min_val: int, max_val: int) -> int:
        """Return a gaussian-distributed int in [min_val, max_val].

        Matches C# Rng.NextGaussianInt: uses rejection sampling (re-rolls
        until the result is within range) rather than clamping.
        """
        while True:
            u1 = 1.0 - self._rng.sample()
            u2 = 1.0 - self._rng.sample()
            z = math.sqrt(-2.0 * math.log(u1)) * math.sin(2.0 * math.pi * u2)
            val = round(mean + stddev * z)
            if min_val <= val <= max_val:
                return val

    def fork(self) -> Rng:
        """Create a child RNG with a derived seed."""
        return Rng(self.next_int(0, INT_MAX_EXCLUSIVE))
