# Break It: Free/Busy Math

## Challenge 1: Closed intervals

In `find_conflicts`, change `a.end > o.start` to `a.end >= o.start`. Which assert fails? Now
think about who is hurt: someone with back-to-back meetings.

**Hint:** Every meeting that starts when the previous one ends becomes a "conflict".

## Challenge 2: Add eight hours

In `working_intervals`, compute the end as `start + timedelta(hours=8)` instead of placing 17:00.
Run the DST assertions. Which days are wrong, in which direction?

**Hint:** A 09:00-17:00 day survives, because the clock change happens at 02:00, before 09:00.
Use `working_hours="00:00-08:00"` on 2026-03-08 in New York: the wall clock says 8 hours, but only
7 real hours pass between 00:00 and 08:00 that day.

## Challenge 3: Forget to merge

Remove the `merge` call from `busy_from`. Does `subtract` still work? Feed it two overlapping
meetings and find out.

**Hint:** `subtract` assumes sorted, disjoint busy intervals. With overlap, a later short busy
block can move the cursor backwards.

## Challenge 4: Use naive datetimes

Make `free_slots` build its intervals from naive datetimes in the local zone, then run the
fall-back day. How long is the day? Which hour is counted once instead of twice?

**Hint:** The repeated 01:00-02:00 collapses into one hour.

## Challenge 5: Transparent but important

An all-day "Out of office" event is opaque. With the defaults, does it block your free time? Is
that what you would want an agent to assume? How would you let the caller choose?

**Hint:** `include_all_day`. The point is that the default is a policy, so say it in the tool's
description.
