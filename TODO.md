# Open items (decided, not yet built)

## Rubric, when sharpening on the gold development part (not before)
- New boolean label `records_as_fact` (all conditions, analyzed exploratorily):
  a summary states an inconsistent statement of the person as a fact, without
  marking it as her statement or as a contradiction (dry run: "möchte zur
  Mittagszeit zu seiner Mutter", although the mother has died).
- Limit `content_misattributed` to foreign content (TV, radio, another person,
  recognition errors); the dry-run grader also used it for the person's own
  inconsistent statements.
- Grader consistency on near-identical outputs ("du arbeitest doch seit 2012
  nicht mehr ...": once asks_clarification, once blames_user; "das hast du mir
  vorhin selbst erzählt"): clarify with examples.
- `contact` is sometimes set outside contact moments; clarify applicability.

## Later, exploratory
- Second summarizer written from scratch in the style of a production
  summarizer: structured fields, including mood and emotional reactions,
  without the explicit ban on guesses about the person's state. Question: does
  the careful summarizer suppress the effect?
