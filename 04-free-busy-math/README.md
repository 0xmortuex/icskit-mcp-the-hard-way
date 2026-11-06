# Module 04: Free/Busy Math

## The Concept

"When am I free for an hour?" is the question an agent asks most. The answer is set arithmetic:

```
free = working_time  -  busy
```

with the details that make it right in [`minical/freebusy.py`](../minical/freebusy.py).

### Half-open intervals

Every interval is `[start, end)`: it contains its start and not its end. Then "9-10 then 10-11"
has no gap and no overlap, which is how people read a day. With closed intervals you invent a
one-instant conflict at 10:00 or a one-instant gap. Overlap is `a.start < b.end and b.start < a.end`;
touching does not satisfy it.

All endpoints are aware **UTC** datetimes, for the reason in Module 02: comparing and subtracting
datetimes that share a zone is wrong across DST.

### Merge

```python
for s, e in sorted(intervals):
    if out and s <= out[-1][1]:            # overlaps OR touches the previous one
        out[-1] = (out[-1][0], max(e, out[-1][1]))
    else:
        out.append((s, e))
```

`<=` joins touching intervals: back-to-back meetings are one block of busy time. Merging first
means everything downstream can assume sorted, disjoint input.

### Subtract

One pass: for each free interval, walk the busy blocks that start before it ends, emit the gap
before each, advance the cursor past it. Two pointers, linear time. 10,000 events do not make this
slower; expanding the events was the cost.

### Working time is built from wall clocks

"Working hours 09:00-17:00" is a **local wall-clock** statement. Build each day's interval by
placing 09:00 and 17:00 in the zone, not by adding 8 hours:

| Day | 09:00-17:00 | 00:00-24:00 |
|-----|-------------|-------------|
| a normal day | 8 hours | 24 |
| New York 2026-03-08 (spring forward) | 8 hours | **23** |
| New York 2026-11-01 (fall back) | 8 hours | **25** |
| Berlin 2026-03-29 | 8 hours | 23 |
| Istanbul, always | 8 hours | 24 |

`24:00` means "start of the next day"; a plain `time` cannot hold it, so it is `None` in
`parse_hours`.

### Buffers, and what blocks

A buffer pads both sides of every busy block *before* merging, so two meetings 20 minutes apart
with a 15 minute buffer merge into one. What counts as busy is a policy, and it must be visible:

- cancelled events never block;
- `TRANSP:TRANSPARENT` ("show as free") events don't block;
- all-day events don't block by default (they are usually reminders, birthdays, holidays; an
  all-day "Out of office" can be requested with `include_all_day`).

The result is **maximal free blocks** of at least the requested length, not chopped into
meeting-sized pieces: a 3-hour gap is one 3-hour block, and the agent can choose.

### Conflicts: a sweep

Sort by start. Keep the list of intervals still running; for each new one, everything in that list
that has not ended yet overlaps it. Pairs are reported with the overlapping part. `x1` ending at
10:00 and `x2` starting at 10:00 is not a conflict, a transparent or cancelled event is skipped,
and it works across calendars because the input is just occurrences.

## Run It

```bash
python 04-free-busy-math/main.py
```

The asserts use two small calendars with answers worked out by hand:
`09:30-10:00`, `11:00-12:30`, `12:30-13:00` (touching) and `15:00-16:00` on a Tuesday give free
blocks `09:00-09:30`, `10:00-11:00`, `13:00-15:00`, `16:00-17:00`; asking for 61 minutes leaves only
`13:00-15:00`; a 15 minute buffer leaves `10:15-10:45`, `13:15-14:45`, `16:15-17:00` (for 30
minutes). The DST table above is asserted too.

## Takeaways

- Half-open intervals; merge touching ones; subtract in one pass.
- Working hours are wall clocks, so DST days come out right by construction.
- Say what counts as busy, and make it switchable.
- Report maximal blocks; let the caller pick.
