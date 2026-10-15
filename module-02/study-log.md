# Module 2 — Study Log

[← Portfolio home](../README.md) · [Module 2 README](./README.md) · [Course module](https://github.com/iotempire/iotempire-teaching/blob/main/full-classes/hsbi-databases-10d/modules/02-data-contracts-and-legacy-schemas.md)

> Task A (~30 min pod study), Task B (four sketches), Task C (pod-pair exchange).
> Pod: _____ · Date: _____

---

## 1. References I used

> The source, and **the one concept I understood best from it**. Credit first.

| Source (link / book / video) | The one thing it taught me |
|---|---|
| [Entity-relationship model wiki](https://en.wikipedia.org/wiki/Entity%E2%80%93relationship_model) | Learned about Cardinality, Entities (a real-world object, place, person, or concept that has an independent existence and about which you want to store data), Entity types (the category/template that , Entity sets, and relations. |
| [Enhanced entity-relationship model wiki](https://en.wikipedia.org/wiki/Enhanced_entity%E2%80%93relationship_model) | Learned that EER is basically the upgraded version of the original ER diagram that we use to design databases. It adds superclasses/subclasses, inheritance, specialization, generalization, and more. |
| [Surrogate Key wiki](https://en.wikipedia.org/wiki/Surrogate_key) | Learned that a surrogate key is an ID number that a system makes up just to tell records apart. |
| [Natural Key wiki](https://en.wikipedia.org/wiki/Natural_key) | Learned that a natural key identifies something using information that *already* exists in the real world and actually means something. |


---

## 2. Things I googled

> One line each: the term or question, what I found, the URL.

| What I searched | What I found | Source |
|---|---|---|
|  |  |  |
|  |  |  |

---

## 3. Remarkable things

> Surprises, "aha"s, counterexamples. The module's own example: *"a name looked like a key but had duplicates."*

-
-
-

---

## 4. LLM Q&A

> For each prompt: the prompt, a 2–3 line summary of the answer, and **how I verified it** — including where it was wrong, vague, or over-confident.

### Prompt 1

**Prompt:**

**Answer (2–3 lines):**

**How I verified it:**

**Where it was wrong / vague / over-confident:**

### Prompt 2

**Prompt:**

**Answer (2–3 lines):**

**How I verified it:**

**Where it was wrong / vague / over-confident:**

### Prompt 3

**Prompt:**

**Answer (2–3 lines):**

**How I verified it:**

**Where it was wrong / vague / over-confident:**

---

## 5. Two best found ER sketches

> Hunt for example sketches, then compile down to the best **two**. For each: source/credit, the image (screenshot or my own redraw), and **what it taught me that the others did not show**.

### Sketch 1 — _title_

- **Source:**
- **Image:** `![](./img/sketch-1.png)`
- **What it showed me that others did not:**

### Sketch 2 — _title_

- **Source:**
- **Image:** `![](./img/sketch-2.png)`
- **What it showed me that others did not:**

---

## 6. Task B — four sketches from words

> Entities, attributes, relationships + cardinality for each description, then a sketch.

### 6.1 — 1:1 · machine ↔ nameplate

- **Entities / attributes:**
- **Cardinality and where the key goes:**
- **Separate entity or just an attribute? Why:**
- **Sketch:**

### 6.2 — 1:n · machine → sensors

- **Entities / attributes:**
- **Which side holds the foreign key, and why:**
- **Sketch:**

### 6.3 — m:n · work orders ↔ parts

- **Entities / attributes:**
- **Junction table and its key:**
- **How "an order lists a part only once" is enforced:**
- **Sketch:**

### 6.4 — entity vs. attribute vs. relationship · maintenance job

- **Is the job a relationship or an entity? My answer and why:**
- **Is the technician an entity or just a name? My answer and why:**
- **Sketch:**

### 6.5 — The proof

> `CREATE TABLE` for my favourite sketch, two inserted rows, and the `COUNT` query that demonstrates the cardinality.

```sql

```

**Result:**

```

```

**What this proves:**

---

## 7. Agreed learning (pod discussion)

> Task C. The 3–5 points both pods stand behind, what I learned from the other pod, and any disagreement we left open.

**Pod we paired with:**

**Agreed points:**

1.
2.
3.

**What I changed in this log after the exchange:**

**Disagreement we left open:**

**Image we posted in Discord:** _link_ — chosen because:
