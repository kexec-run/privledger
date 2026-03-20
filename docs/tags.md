# Tags Specification

## Purpose

Tags are **atomic, observable labels** applied to a session.

They are used for:

* filtering
* correlation
* long-term behavioral analysis

Tags must remain:

* specific
* consistent
* low-ambiguity
* low-cognitive-load
* low-abstraction

---

## General Rules

### 1. Use only concrete, observable concepts

Allowed:

* `smoking`
* `exercise`
* `fatigue`

Avoid:

* `life`
* `things`
* `activity`

### 2. Cognitive Load Constraint

Tags must be usable even when you are:

* tired
* stressed
* distracted
* mentally unwell

Implications:

* Tags must be easy to recall instantly
* No thinking-heavy interpretation
* If you hesitate, skip or pick the closest obvious one

**Rule:** If a tag takes effort to decide, it is too complex.

### 3. Low Abstraction Rule (5-second test)

This rule applies at two levels:

1. **Tag creation**
2. **Tag selection (usage)**

#### A. Tag Creation Rule

When introducing a new tag, apply the 5-second test:

> Think of a real situation and list 5 possible interpretations in under 5 seconds.

If multiple meanings appear, the tag is too abstract.

Example:

```text
"work" → could mean:
- job
- chores
- family responsibility
- studying
- programming
```

This is ambiguous → **reject**

Instead, split into concrete tags:

```text
job, chores, programming
```

#### Tag Definition Requirement

Every tag must clearly represent **one of the following**:

* **Initiator / trigger** (what started the state)
  * curiosity
  * smoking

* **End state / outcome** (what you ended up in)
  * fatigue
  * recovery

If a tag does not clearly fall into one of these, it is too vague.

#### B. Tag Selection Rule (Usage)

When tagging a session:

> In under 5 seconds, list 4–5 possible tags.

Example:

```text
programming, job, fatigue, procrastination, systems
```

Pick the **most direct and observable ones**.

Do not overthink.
Do not optimize for perfect classification.

#### Principle

* Creation → eliminate ambiguity
* Usage → minimize thinking

If a tag requires thinking at either stage, it is too abstract.

### 4. Tags are flat (no hierarchy)

Do not encode relationships:

```
❌ health.exercise
❌ work.programming
```

Use:

```
✅ exercise
✅ programming
```

### 5. Tags are not categories

Do not add grouping tags:

```
❌ habit
❌ bad_habit
❌ work
```

Use specific signals instead.

### 6. Maximum 5 tags per entry

Choose only the strongest signals.

### 7. Tags must be lowercase

```
✅ smoking
❌ Smoking
❌ SMOKING
```

---

## Tag Definitions

### Work / Cognitive

#### systems

System-level thinking, architecture, infrastructure.

Do not use for coding.

#### programming

Writing or debugging code.

#### job

Employment-related activity.

Use when:

* working for your employer
* meetings
* office or admin work

Do not use for:

* programming (use `programming`)
* chores (use `chores`)
* personal projects

#### planning

Thinking about future actions, scheduling, structuring work.

#### curiosity

Exploration without immediate goal.

Used instead of "learning" because it captures the **trigger**, not the outcome.

### Health / Body

#### exercise

Physical activity.

#### sleep

Sleep context.

#### nutrition

Food and diet.

#### fatigue

Low energy, exhaustion.

**Important:**
Fatigue is the **primary performance-degrading signal**.

Use this for:

* illness impact
* burnout
* tiredness

Even if health issues exist, only tag if it leads to fatigue.

#### recovery

Intentional recovery from fatigue.

> **Fatigue vs Recovery:** `fatigue` = degraded state, `recovery` = active restoration. They represent opposite phases — do not use both unless both clearly occurred.

### Life / Context

#### social

Interaction with people.

#### travel

Movement between locations.

**Rule:**

* One-off or irregular → `travel`
* Routine commute → NOT travel (likely part of `job`)

#### chores

Routine responsibilities.

#### family

Family-related interaction.

#### love

Romantic / relationship context only.

### Behavior / Risk

#### procrastination

Avoiding intended work.

#### smoking

**Only the act of smoking.**

Do not use for:

* thoughts
* urges
* discussions

Strictly behavioral.

### Event Tags

#### reset

Major state change or restart.

Use when:

* clear break in routine
* intentional restart

**Do not overuse.**
This is a high-weight event marker.

---

## Tag Selection Strategy

When tagging:

1. Identify **what happened**
2. Identify **what defined the session**
3. Add up to 5 strongest signals

Example:

```
["programming", "fatigue", "procrastination"]
```

### Focus Domain Rules

* Only **one** focus domain allowed
* Must be selected from tags
* Represents the **dominant undertone**

#### Selection Rule

If you have multiple tags and are unsure:

> Pick the one that defined the session or influenced everything else.

#### Focus Domain Can Be Empty

```
focus_domain = null
```

This is valid.

No data is also data.

Do NOT force a focus domain.

---

## What Not To Do

* Do not invent new tags casually
* Do not use vague terms
* Do not over-tag
* Do not force meaning

---

## Summary

Tags are:

* simple
* specific
* observable
* low-effort

They are not:

* categories
* abstractions
* opinions

Keep them minimal and usable under all conditions.
