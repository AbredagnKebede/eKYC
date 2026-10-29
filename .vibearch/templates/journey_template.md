# Journey: <human-readable journey name>
journey_id: J-<nn>
covers: AS-<nn>
priority: critical | high | normal
graph_nodes: [<node_id>, <node_id>]

<!--
  Written by the journey_mapper agent (Stage 4.5), one file per acceptance scenario in
  system_guide.md §8. Validated by .vibearch/scripts/check_journeys.py.

  Rules that matter:
  * Every field above is required. `graph_nodes` is the coverage anchor — it must list
    every system_graph.json node this journey touches.
  * User Steps are BLACK BOX. Write only what a user does and observes. No function
    names, no table names, no internal calls.
  * Every assertion point needs an `AP-<n>` id. The journey loop's tests must cite that
    id, and .vibearch/scripts/check_journey_coverage.py fails the loop if any AP is uncited.
    This is what replaces line coverage for journey loops.
  * Failure modes listed here feed loop_chaos. Give each one a `CH-<n>` id.
  Delete this comment when filling the file in.
-->

## User Steps (black-box perspective)

1. User <does X>
2. System responds with <Y>
3. User sees <Z>

## Required System Components (what must be running)

- <Service A> — with a real database
- <Worker B> — as a running process consuming the real queue
- <External API C> — real sandbox endpoint, not a mock
- <Queue/topic name> — the real broker

## Assertion Points (what proves this worked)

- AP-1 Database: <table> row exists with <column>=<value>
- AP-2 Queue: `<event.name>` was consumed, not left pending — consumer offset advanced
- AP-3 External API: `<operation>` returned 200 and a `<id field>` is present
- AP-4 API response: `<endpoint>` returned <status> with <field>=<value>
- AP-5 Latency: user-visible result within <n> seconds (ties to system_guide.md §7 SLOs)

## Failure Modes to Test

- CH-1 Timeout at step <n> — expected behavior: <retry / fail-closed / user message>
- CH-2 Duplicate submission of step <n> — expected: idempotent, one row, one side effect
- CH-3 <Service/worker> restarts during step <n> — expected: <resumes / compensates>
- CH-4 <Credential/token> expires mid-journey — expected: <refresh / fail-closed>

## Notes

<Anything a builder needs that is not obvious from system_guide.md. Cite spec anchors as
`system_guide.md §N.M`. Delete this section if empty.>
