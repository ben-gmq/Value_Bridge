# Value Bridge — process flow conversion prompt pack (`vb-process-flow/2.0`)

## Before you start (for the consultant — read this, do not paste it)

- **Use Claude Enterprise under FTC's own account, and nothing else.** No Copilot, no ChatGPT, no personal
  Claude account, no other AI service. Client content must not go into any other AI: its terms have not been checked.
- **Remove personal data yourself before you paste anything** — people's names, e-mail addresses, phone numbers,
  anything that identifies a person. Use a role or a department instead ("Sales administrator", not "Jane Tan").
  The AI is not asked to do this for you.
- **Everything in Value Bridge is confidential**, much of it under client NDAs. Paste only the flow you are
  converting.
- **Read the preview before you commit.** Value Bridge checks the file and lists every step it would add or
  change; the AI's output is a draft, never a decision.

Paste the prompt below into Claude Enterprise, followed by the flow (slide text, a BPMN export, or a description of
a Visio diagram). Save the AI's answer as a `.json` file and import it on the process chart's anchor node.

---

## Prompt (paste this into Claude Enterprise)

You convert one business process flow into a JSON file in the format `vb-process-flow/2.0`. Answer with the JSON
file only — no commentary, no Markdown fence.

The file has this shape:

```
{
  "format": "vb-process-flow/2.0",
  "parent": { "hier_code": "<the code the consultant gives you>", "name": "<the parent's name>" },
  "mode": "merge",
  "external_entities": [ { "key": "X1", "ext_number": null, "name": "Customer", "kind": null } ],
  "steps": [
    { "key": "S1", "br_number": null, "hier_code": null, "row_version": null,
      "name": "Receive order", "description": "What happens in this step.",
      "performer": { "kind": "ORG_ROLE", "code": "SALES-ADMIN" },
      "triggers": [ { "name": "Customer calls", "kind": "EVENT" } ],
      "inputs": ["Customer order"], "outputs": ["Sales order"],
      "external_flows": [ { "external": "X1", "direction": "I", "data_entity": "Customer order" } ],
      "source_ref": "slide 4, shape 12" }
  ]
}
```

Rules:

1. **One step per activity box**, in the order the flow runs. `key` is `S1`, `S2`, … — unique in the file, letters,
   digits, `_` or `-` only.
2. **Write `br_number`, `hier_code` and `row_version` as `null` on every step you make.** They come only from a
   file exported by Value Bridge. Never invent them.
3. `name` is the activity's name, at most 200 characters, unique in the file. `description` is one or two plain
   sentences of what happens; leave it out if the source says nothing.
4. **Performer** — who does the step:
   - a department: `{ "kind": "ORG_UNIT", "code": "<code>" }`
   - a position: `{ "kind": "ORG_ROLE", "code": "<code>" }`
   - an IT system: `{ "kind": "APPLICATION", "code": "<code>" }`
   - an AI agent: `{ "kind": "AI", "label": "<its name>" }`
   Use a code only if the consultant gave you the list of codes. Otherwise leave `performer` out entirely.
5. **Triggers** — what starts the step: `{ "name": "…", "kind": "EVENT" }` for something that happens, or
   `"kind": "TIME"` for a schedule ("Every Monday"). Leave `triggers` out if the source shows none.
6. **Inputs and outputs** — the information the step reads and produces, each a short business name
   ("Sales order", "Credit decision"). Use the same name every time the same information appears.
7. **Outside parties** — a customer, supplier, bank or authority the flow exchanges information with: one entry in
   `external_entities` (`key` `X1`, `X2`, …, `ext_number` `null`, `name`, `kind` `null`), and on the step an
   `external_flows` entry naming it by `key`, with `direction` `"I"` (it sends to the step) or `"O"` (the step
   sends to it), and the information exchanged as `data_entity`.
8. **Leaving a list out is not the same as an empty list.** Leave out `triggers`, `inputs`, `outputs` or
   `external_flows` when the source says nothing about them. Write `[]` only when the source clearly shows there
   are none.
9. **No arrows and no swimlanes.** Do not add `edges`, `lanes` or any key not shown above — the file is refused.
   Value Bridge draws the order and the lanes itself from inputs, outputs and performers.
10. `source_ref` says where the step came from in the source ("slide 4, shape 12"), at most 200 characters, so the
    consultant can check it.
11. `"mode"` is always `"merge"`.
