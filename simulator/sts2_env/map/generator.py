"""Standard act map generator.

Implements the StandardActMap algorithm from MegaCrit.Sts2.Core.Map/StandardActMap.cs.
7-column grid, 7 random paths, crossover prevention, room type assignment with
all placement constraints.
"""

from __future__ import annotations

from sts2_env.core.enums import MapPointType
from sts2_env.core.rng import Rng
from sts2_env.map.map_point import MapCoord, MapPoint


MAP_WIDTH = 7
MAP_ITERATIONS = 7
GOLDEN_PATH_POINT_TYPES = (
    MapPointType.MONSTER,
    MapPointType.UNKNOWN,
    MapPointType.MONSTER,
    MapPointType.REST_SITE,
    MapPointType.MONSTER,
    MapPointType.REST_SITE,
    MapPointType.UNKNOWN,
    MapPointType.TREASURE,
    MapPointType.UNKNOWN,
    MapPointType.TREASURE,
    MapPointType.UNKNOWN,
    MapPointType.SHOP,
    MapPointType.ELITE,
    MapPointType.REST_SITE,
    MapPointType.ELITE,
    MapPointType.REST_SITE,
)


class ActMap:
    """A generated act map containing all map points and edges."""

    def __init__(self, num_rooms: int):
        self.map_length = num_rooms + 1  # rows: 0=start, 1..N-1=rooms, N-1+1=boss
        self._grid: dict[tuple[int, int], MapPoint] = {}
        self.boss_point: MapPoint | None = None
        self.start_point: MapPoint | None = None

    def get_or_create(self, col: int, row: int) -> MapPoint:
        key = (col, row)
        if key not in self._grid:
            self._grid[key] = MapPoint(MapCoord(col, row))
        return self._grid[key]

    def get_point(self, coord: MapCoord) -> MapPoint | None:
        return self._grid.get((coord.col, coord.row))

    def get_row(self, row: int) -> list[MapPoint]:
        return sorted(
            [p for p in self._grid.values() if p.row == row],
            key=lambda p: p.col,
        )

    def all_points(self) -> list[MapPoint]:
        return list(self._grid.values())

    def room_points(self) -> list[MapPoint]:
        """All points that are actual rooms (exclude start/boss meta-nodes)."""
        return [
            p for p in self._grid.values()
            if p is not self.start_point and p is not self.boss_point
        ]


def generate_golden_path_map(player_count: int = 1) -> ActMap:
    point_types = list(GOLDEN_PATH_POINT_TYPES)
    if player_count > 1:
        point_types.pop(2)

    act_map = ActMap(len(point_types))
    start = act_map.get_or_create(3, 0)
    start.point_type = MapPointType.ANCIENT
    act_map.start_point = start
    boss = act_map.get_or_create(3, len(point_types) + 1)
    boss.point_type = MapPointType.BOSS
    act_map.boss_point = boss

    previous = start
    for row, point_type in enumerate(point_types, start=1):
        point = act_map.get_or_create(3, row)
        point.point_type = point_type
        previous.add_child(point)
        previous = point
    previous.add_child(boss)
    return act_map


def _has_invalid_crossover(act_map: ActMap, current: MapPoint, target_col: int) -> bool:
    """Check if moving from current to target_col would create a crossing edge.

    Matches C# StandardActMap.HasInvalidCrossover: checks if the point at
    (target_col, current.row) has a child going in the opposite direction.
    """
    direction = target_col - current.col
    # Straight up (direction==0) never crosses
    if direction == 0:
        return False

    blocker = act_map.get_point(MapCoord(target_col, current.row))
    if blocker is None:
        return False

    for child in blocker.children:
        child_dir = child.col - blocker.col
        if child_dir == -direction:
            return True

    return False


def _generate_next_coord(act_map: ActMap, current: MapPoint, rng: Rng) -> tuple[int, int]:
    """Generate the next coordinate for path generation."""
    col = current.col
    min_col = max(0, col - 1)
    max_col = min(col + 1, MAP_WIDTH - 1)

    directions = [-1, 0, 1]
    rng.shuffle(directions)

    for d in directions:
        if d == -1:
            target_col = min_col
        elif d == 0:
            target_col = col
        else:
            target_col = max_col
        target_row = current.row + 1
        if not _has_invalid_crossover(act_map, current, target_col):
            return (target_col, target_row)

    # Fallback: straight up (shouldn't normally happen)
    return (col, current.row + 1)


def _path_generate(act_map: ActMap, start: MapPoint, rng: Rng) -> None:
    """Walk a path from start upward to the top row."""
    current = start
    while current.row < act_map.map_length - 1:
        col, row = _generate_next_coord(act_map, current, rng)
        next_point = act_map.get_or_create(col, row)
        current.add_child(next_point)
        current = next_point


def _is_type_valid_for_point(
    point: MapPoint,
    point_type: MapPointType,
    map_length: int,
) -> bool:
    """Check all five placement constraint rules."""
    row = point.row

    # Rule 1: Lower map (row < 5) -- no RestSite or Elite
    if row < 5 and point_type in (MapPointType.REST_SITE, MapPointType.ELITE):
        return False

    # Rule 2: Upper map (row >= mapLength - 3) -- no RestSite
    if row >= map_length - 3 and point_type == MapPointType.REST_SITE:
        return False

    # Rule 3: Parent adjacency -- Elite, RestSite, Treasure, Shop can't match parent type
    restricted = {MapPointType.ELITE, MapPointType.REST_SITE, MapPointType.TREASURE, MapPointType.SHOP}
    if point_type in restricted:
        for parent in point.parents:
            if parent.point_type == point_type:
                return False

    # Rule 4: Child adjacency -- same restricted types can't match child type
    if point_type in restricted:
        for child in point.children:
            if child.point_type == point_type:
                return False

    # Rule 5: Sibling uniqueness -- RestSite, Monster, Unknown, Elite, Shop
    sibling_restricted = {
        MapPointType.REST_SITE, MapPointType.MONSTER, MapPointType.UNKNOWN,
        MapPointType.ELITE, MapPointType.SHOP,
    }
    if point_type in sibling_restricted:
        for sib in point.siblings():
            if sib.point_type == point_type:
                return False

    return True


def _assign_room_types(
    act_map: ActMap,
    rng: Rng,
    num_elites: int,
    num_shops: int,
    num_unknowns: int,
    num_rests: int,
    replace_treasure_with_elite: bool = False,
) -> None:
    """Assign room types to all map points.

    Matches C# AssignPointTypes: fixed rows first, then cycling-queue
    assignment over shuffled unassigned points, leftover = Monster.
    Boss and Ancient assigned AFTER the pool pass (matching C# order).
    """
    map_length = act_map.map_length
    row_count = map_length

    # Fixed: last room row = RestSite
    for p in act_map.get_row(row_count - 1):
        p.point_type = MapPointType.REST_SITE

    # Fixed: treasure row (rowCount - 7)
    treasure_row = row_count - 7
    if treasure_row > 0:
        for p in act_map.get_row(treasure_row):
            if replace_treasure_with_elite:
                p.point_type = MapPointType.ELITE
            else:
                p.point_type = MapPointType.TREASURE

    # Fixed: first room row = Monster
    for p in act_map.get_row(1):
        p.point_type = MapPointType.MONSTER

    # Build the random pool as a queue (C# uses Queue<MapPointType>)
    from collections import deque
    pool_list: list[MapPointType] = []
    pool_list.extend([MapPointType.REST_SITE] * num_rests)
    pool_list.extend([MapPointType.SHOP] * num_shops)
    pool_list.extend([MapPointType.ELITE] * num_elites)
    pool_list.extend([MapPointType.UNKNOWN] * num_unknowns)
    pool: deque[MapPointType] = deque(pool_list)

    # Collect unassigned points and shuffle (C# StableShuffle on all map points)
    unassigned = [
        p for p in act_map.room_points()
        if p.point_type == MapPointType.UNASSIGNED
    ]
    rng.shuffle(unassigned)

    # Assign from pool with cycling queue (matches C# GetNextValidPointType)
    for point in unassigned:
        assigned_type = _get_next_valid_type_from_queue(pool, point, map_length)
        point.point_type = assigned_type

    # Any remaining unassigned points become Monster
    for point in act_map.room_points():
        if point.point_type == MapPointType.UNASSIGNED:
            point.point_type = MapPointType.MONSTER

    # Boss and Ancient assigned last (matches C# order)
    if act_map.boss_point:
        act_map.boss_point.point_type = MapPointType.BOSS
    if act_map.start_point:
        act_map.start_point.point_type = MapPointType.ANCIENT


def _get_next_valid_type_from_queue(
    pool: 'deque[MapPointType]',
    point: MapPoint,
    map_length: int,
) -> MapPointType:
    """Try each type in the queue; if valid, consume it. Otherwise re-enqueue.

    Matches C# GetNextValidPointType: cycles through the entire queue once.
    Returns UNASSIGNED if no valid type found (caller converts to Monster).
    """
    for _ in range(len(pool)):
        candidate = pool.popleft()
        if _is_type_valid_for_point(point, candidate, map_length):
            return candidate
        pool.append(candidate)  # put it back at the end
    return MapPointType.UNASSIGNED


def _center_grid(act_map: ActMap) -> None:
    """If left columns empty but right not (or vice versa), shift by 1."""
    points = act_map.all_points()
    if not points:
        return

    cols_used = {p.col for p in points}
    left_empty = 0 not in cols_used and 1 not in cols_used
    right_empty = 5 not in cols_used and 6 not in cols_used

    if left_empty and not right_empty:
        shift = -1  # shift left to center (matches C# num = -1)
    elif right_empty and not left_empty:
        shift = 1   # shift right to center (matches C# num = 1)
    else:
        return

    # Rebuild grid with shifted coordinates
    new_grid: dict[tuple[int, int], MapPoint] = {}
    for p in points:
        new_col = max(0, min(MAP_WIDTH - 1, p.coord.col + shift))
        p.coord = MapCoord(new_col, p.coord.row)
        new_grid[(new_col, p.coord.row)] = p
    act_map._grid = new_grid


def _map_point_type_counts(
    rng: Rng,
    *,
    ascension_level: int,
    act_index: int,
) -> tuple[int, int, int, int]:
    has_swarming = ascension_level >= 1
    has_gloom = ascension_level >= 6

    def base_counts(source: Rng) -> tuple[int, int, int, int]:
        return (
            round(5 * (1.6 if has_swarming else 1.0)),
            3,
            source.next_gaussian_int(mean=12, stddev=1, min_val=10, max_val=14),
            source.next_gaussian_int(mean=5, stddev=1, min_val=3, max_val=6),
        )

    if act_index in (0, 1):
        num_rests = rng.next_gaussian_int(mean=7, stddev=1, min_val=6, max_val=7)
        if has_gloom:
            num_rests -= 1
        num_elites, num_shops, num_unknowns, _ = base_counts(rng)
        return num_elites, num_shops, num_unknowns, num_rests

    if act_index == 2:
        count_rng = Rng(rng.seed, counter=rng.counter)
        _, _, num_unknowns, _ = base_counts(count_rng)
        num_rests = rng.next_int_exclusive(5, 7)
        if has_gloom:
            num_rests -= 1
        num_elites, num_shops, _, _ = base_counts(rng)
        return num_elites, num_shops, num_unknowns - 1, num_rests

    num_elites = round(5 * (1.6 if has_swarming else 1.0))
    num_shops = 3
    num_unknowns = rng.next_gaussian_int(mean=12, stddev=1, min_val=10, max_val=14)
    num_rests = rng.next_gaussian_int(mean=5, stddev=1, min_val=3, max_val=6)

    return num_elites, num_shops, num_unknowns, num_rests


def _spoils_allowed_columns(row: int, treasure_row: int, map_length: int) -> tuple[int, int]:
    center = MAP_WIDTH // 2
    distance_to_treasure = abs(row - treasure_row)
    rows_to_top = map_length - 1 - row
    top_width = min(center, max(0, rows_to_top) + 1)
    spread = min(center, min(distance_to_treasure, top_width))
    return max(0, center - spread), min(MAP_WIDTH - 1, center + spread)


def _spoils_centered_directions(current_col: int) -> list[int]:
    center = MAP_WIDTH // 2
    direction = 0
    if center > current_col:
        direction = 1
    elif center < current_col:
        direction = -1
    directions: list[int] = []
    if direction:
        directions.append(direction)
    directions.append(0)
    if direction:
        directions.append(-direction)
    if -1 not in directions:
        directions.append(-1)
    if 1 not in directions:
        directions.append(1)
    return directions


def _spoils_next_column(current_col: int, direction: int) -> int:
    if direction < 0:
        return max(0, current_col - 1)
    if direction > 0:
        return min(MAP_WIDTH - 1, current_col + 1)
    return current_col


def _spoils_generate_next_coord(
    act_map: ActMap,
    current: MapPoint,
    rng: Rng,
    treasure_row: int,
) -> tuple[int, int]:
    row = current.row + 1
    min_col, max_col = _spoils_allowed_columns(row, treasure_row, act_map.map_length)
    distance_to_treasure = treasure_row - current.row
    if distance_to_treasure > 3:
        directions = [-1, 0, 1]
        rng.shuffle(directions)
    elif distance_to_treasure > 0:
        directions = _spoils_centered_directions(current.col)
    else:
        directions = [-1, 0, 1]
        rng.shuffle(directions)

    for direction in directions:
        next_col = _spoils_next_column(current.col, direction)
        if next_col < min_col or next_col > max_col:
            continue
        if _has_invalid_crossover(act_map, current, next_col):
            continue
        point = act_map.get_point(MapCoord(next_col, row))
        parent_ok = point is None or current in point.parents or len(point.parents) < 3
        child_ok = current is act_map.start_point or len(current.children) < 3 or (
            point is not None and point in current.children
        )
        if parent_ok and child_ok:
            return next_col, row

    center = MAP_WIDTH // 2
    fallback = max(min_col, min(max_col, center))
    if abs(fallback - current.col) > 1:
        step = 1 if fallback > current.col else -1
        fallback = max(min_col, min(max_col, current.col + step))
    if _has_invalid_crossover(act_map, current, fallback):
        fallback = max(min_col, min(max_col, current.col))
    return fallback, row


def _spoils_path_generate(act_map: ActMap, start: MapPoint, rng: Rng, treasure_row: int) -> None:
    current = start
    while current.row < act_map.map_length - 1:
        col, row = _spoils_generate_next_coord(act_map, current, rng, treasure_row)
        next_point = act_map.get_or_create(col, row)
        current.add_child(next_point)
        current = next_point


def _redirect_to_spoils_treasure(act_map: ActMap, stray: MapPoint, treasure: MapPoint) -> None:
    for parent in list(stray.parents):
        parent.remove_child(stray)
        parent.add_child(treasure)
    for child in list(stray.children):
        stray.remove_child(child)
        treasure.add_child(child)
    act_map._grid.pop((stray.col, stray.row), None)


def _is_spoils_type_valid(point: MapPoint, point_type: MapPointType, map_length: int) -> bool:
    if point.row < 5 and point_type in (MapPointType.REST_SITE, MapPointType.ELITE):
        return False
    if point.row >= map_length - 3 and point_type == MapPointType.REST_SITE:
        return False
    restricted = {MapPointType.ELITE, MapPointType.REST_SITE, MapPointType.TREASURE, MapPointType.SHOP}
    if point_type in restricted:
        if any(parent.point_type == point_type for parent in point.parents):
            return False
        if any(child.point_type == point_type for child in point.children):
            return False
    sibling_restricted = {
        MapPointType.REST_SITE,
        MapPointType.MONSTER,
        MapPointType.UNKNOWN,
        MapPointType.ELITE,
        MapPointType.SHOP,
    }
    if point_type in sibling_restricted and any(sib.point_type == point_type for sib in point.siblings()):
        return False
    return True


def _assign_spoils_room_types(
    act_map: ActMap,
    rng: Rng,
    *,
    num_elites: int,
    num_shops: int,
    num_unknowns: int,
    num_rests: int,
) -> None:
    from collections import deque

    for point in act_map.get_row(act_map.map_length - 1):
        point.point_type = MapPointType.REST_SITE
    for point in act_map.get_row(1):
        if point.point_type == MapPointType.UNASSIGNED:
            point.point_type = MapPointType.MONSTER

    pool_list: list[MapPointType] = []
    pool_list.extend([MapPointType.REST_SITE] * num_rests)
    pool_list.extend([MapPointType.SHOP] * num_shops)
    pool_list.extend([MapPointType.ELITE] * num_elites)
    pool_list.extend([MapPointType.UNKNOWN] * num_unknowns)
    pool: deque[MapPointType] = deque(pool_list)

    points = [p for p in act_map.room_points()]
    rng.shuffle(points)
    for point in points:
        if point.point_type != MapPointType.UNASSIGNED:
            continue
        for _ in range(len(pool)):
            candidate = pool.popleft()
            if _is_spoils_type_valid(point, candidate, act_map.map_length):
                point.point_type = candidate
                break
            pool.append(candidate)

    for point in act_map.room_points():
        if point.point_type == MapPointType.UNASSIGNED:
            point.point_type = MapPointType.MONSTER
    if act_map.boss_point:
        act_map.boss_point.point_type = MapPointType.BOSS
    if act_map.start_point:
        act_map.start_point.point_type = MapPointType.ANCIENT


def generate_spoils_act_map(
    num_rooms: int,
    rng: Rng,
    ascension_level: int = 0,
    act_index: int = 1,
) -> ActMap:
    num_elites, num_shops, num_unknowns, num_rests = _map_point_type_counts(
        rng,
        ascension_level=ascension_level,
        act_index=act_index,
    )
    act_map = ActMap(num_rooms)
    act_map.start_point = act_map.get_or_create(MAP_WIDTH // 2, 0)
    act_map.boss_point = act_map.get_or_create(MAP_WIDTH // 2, act_map.map_length)
    treasure_row = act_map.map_length - 7
    if treasure_row <= 0 or treasure_row >= act_map.map_length:
        raise ValueError("Treasure row is out of bounds for Spoils Map")

    start_points: list[MapPoint] = []
    for i in range(MAP_ITERATIONS):
        start = act_map.get_or_create(rng.next_int(0, MAP_WIDTH - 1), 1)
        if i == 1:
            while start in start_points:
                start = act_map.get_or_create(rng.next_int(0, MAP_WIDTH - 1), 1)
        start_points.append(start)
        _spoils_path_generate(act_map, start, rng, treasure_row)

    treasure = act_map.get_or_create(MAP_WIDTH // 2, treasure_row)
    treasure.point_type = MapPointType.TREASURE
    for point in list(act_map.get_row(treasure_row)):
        if point is not treasure:
            _redirect_to_spoils_treasure(act_map, point, treasure)

    for point in act_map.get_row(act_map.map_length - 1):
        point.add_child(act_map.boss_point)
    for point in act_map.get_row(1):
        act_map.start_point.add_child(point)

    _assign_spoils_room_types(
        act_map,
        rng,
        num_elites=num_elites,
        num_shops=num_shops,
        num_unknowns=num_unknowns,
        num_rests=num_rests,
    )
    return act_map


def generate_act_map(
    num_rooms: int,
    rng: Rng,
    ascension_level: int = 0,
    replace_treasure_with_elite: bool = False,
    act_index: int = 0,
    num_elites_override: int | None = None,
) -> ActMap:
    """Generate a complete act map.

    Args:
        num_rooms: Number of room rows in this act.
        rng: Seeded RNG for deterministic generation.
        ascension_level: Current ascension level.
        replace_treasure_with_elite: If True, treasure row becomes elite.
        act_index: Which act (0=Overgrowth, 1=Hive, 2=Glory).

    Returns:
        A fully generated ActMap with all room types assigned.
    """
    act_map = ActMap(num_rooms)

    # Create start and boss meta-nodes
    act_map.start_point = act_map.get_or_create(3, 0)
    act_map.boss_point = act_map.get_or_create(3, act_map.map_length)

    # Generate 7 random paths
    start_points: list[MapPoint] = []
    for i in range(MAP_ITERATIONS):
        start_col = rng.next_int(0, MAP_WIDTH - 1)
        start = act_map.get_or_create(start_col, 1)

        # 2nd path must start at a different point
        if i == 1:
            attempts = 0
            while start in start_points and attempts < 100:
                start_col = rng.next_int(0, MAP_WIDTH - 1)
                start = act_map.get_or_create(start_col, 1)
                attempts += 1

        start_points.append(start)
        _path_generate(act_map, start, rng)

    # Connect top row to boss
    for point in act_map.get_row(act_map.map_length - 1):
        point.add_child(act_map.boss_point)

    # Connect starting point to bottom row (row 1)
    for point in act_map.get_row(1):
        act_map.start_point.add_child(point)

    num_elites, num_shops, num_unknowns, num_rests = _map_point_type_counts(
        rng,
        ascension_level=ascension_level,
        act_index=act_index,
    )
    if num_elites_override is not None:
        num_elites = num_elites_override

    # Assign room types
    _assign_room_types(
        act_map, rng,
        num_elites=num_elites,
        num_shops=num_shops,
        num_unknowns=num_unknowns,
        num_rests=num_rests,
        replace_treasure_with_elite=replace_treasure_with_elite,
    )

    # Post-processing
    _center_grid(act_map)

    return act_map
