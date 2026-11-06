# Break It: Time Zones and DST

## Challenge 1: Remove the UTC round trip

In `place()`, replace the body with `return wall.replace(tzinfo=tz)`. Run
`python 02-time-zones-and-dst/main.py`. Which assert fails, and what does `gap.isoformat()`
print instead?

**Hint:** The aware datetime `02:30-05:00` is internally consistent (its UTC time is 07:30Z), but
its wall clock claims a time that was never on any clock in New York that day. Anything that
prints the wall time to a user shows a lie.

## Challenge 2: Compare instead of subtract

Write `a < b` where `a = 01:30 fold=0` and `b = 01:30 fold=1` on 2026-11-01 in New York
(the same wall time, an hour apart). What does Python answer? Now compare `.astimezone(UTC)`.

**Hint:** Same `tzinfo`, so Python compares naive wall clocks and calls them equal.

## Challenge 3: Pick the other policy

Change the overlap rule to "second occurrence" (`fold=1`). Nothing in the module's asserts
about *zones* fails; which behaviour in Module 03/04 changes? Find a weekly event that would now
start an hour later on exactly one day a year.

**Hint:** Think about what a recurring 01:30 event looks like on the fall-back Sunday.

## Challenge 4: Floating time

Write an event with `DTSTART:20260302T090000` (no zone) and ask for it in `Europe/Istanbul` and
in `America/New_York`. Why is the answer different, and why is that *correct*? What would go
wrong if the server used `datetime.now().astimezone().tzinfo` as the default?
