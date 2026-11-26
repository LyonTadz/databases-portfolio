# Task 3 — The injection drill

[← Module 3 home](./README.md) · [`injection_demo.py`](./injection_demo.py)

**Run with:** `uv run python module-03/injection_demo.py`

---

## Output

```
normal   : [(1, 'Customer 1')]
injected : [(1, 'Customer 1'), (2, 'Customer 2'), (3, 'Customer 3')] ...
safe     : []
```

## What each line proves

**`normal`** — one row, as intended. The vulnerable function works perfectly for well-behaved input, which is why this bug ships.

**`injected`** — the payload `' OR '1'='1` returns **all 2,000 customers**. The f-string built:

```sql
SELECT customer_id, name FROM customer WHERE name = '' OR '1'='1'
```

The user's apostrophe closed the string literal, and everything after it was parsed as SQL rather than read as data. The quote is not an awkward character — it is a **context switch**, and the parser has no way to know it came from a text box.

**`safe`** — the same payload returns `[]`. The bound parameter is sent to SQLite separately from the query text, so there is no parse step that could ever see it as syntax. It is treated as what it is: a customer name that happens to contain punctuation, and no customer is called that.

## The support agent's crash

The story's actual failure, reproduced:

```python
vulnerable("O'Brien")
# sqlite3.OperationalError: near "Brien": syntax error
```

No attacker needed. A real surname with an apostrophe produced a syntax error and took the page down — the same bug as the injection, with a different outcome. **The crash and the breach are one defect, not two.** A system that cannot store a name like O'Brien is already broken; that it can also be hijacked is the second symptom.

## Why escaping quotes by hand is not a real fix

I tested the obvious defence — double up every `'` before interpolating:

```python
escaped = payload.replace("'", "''")
# returns 0 rows — the payload is neutralized
```

It works. **And it is still the wrong answer**, for four reasons:

### 1. It only defends string contexts

There are no quotes to escape around a number:

```python
bad = "1 OR 1=1"
conn.execute(f"SELECT customer_id FROM customer WHERE customer_id = {bad}")
# 2000 rows
```

Quote-escaping is irrelevant here and the injection succeeds completely. A fix that depends on the value sitting inside quotes fails the moment someone writes a query where it does not — and nothing warns you.

### 2. It cannot defend identifiers at all

Table and column names cannot be bound as parameters *or* safely escaped the same way. `ORDER BY {user_column}` is injectable and no amount of quote-doubling touches it. The only defence is an allow-list of permitted column names checked in code. Escaping gives false confidence precisely where it offers nothing.

### 3. It is per-dialect, per-encoding, and historically wrong

`''` is SQL-standard, but MySQL also accepts backslash escapes, and there have been real CVEs where a multi-byte character set let an attacker construct a byte sequence that consumed the escaping backslash and freed the quote. Escaping has to be right about the dialect, the connection's character set and the SQLite version. Parameter binding does not care about any of them.

### 4. The responsibility sits in the wrong place

This is the one that actually matters. Escaping makes **correctness depend on every developer remembering, at every call site, forever.** One query written under deadline, one `# TODO: sanitize`, one helper that formats a WHERE clause "just for admin tools" — and the defence is gone, silently, with no error and no failing test.

Bound parameters move the responsibility into the database driver, where it is implemented once and cannot be forgotten. The value never enters the SQL string, so there is no parse step to subvert. The question changes from *"did I remember to escape this?"* to *"is there a `?` here?"* — and the second is visible in code review at a glance.

## The habit

**Never build SQL with string formatting.** Not with `+`, not with `%`, not with f-strings, not "just this once because it's an internal tool". If a value comes from outside the program, it goes in a `?`.

```python
# the only correct shape
conn.execute("SELECT customer_id, name FROM customer WHERE name = ?", (name,))
```

Note the trailing comma — `(name,)` is a one-element tuple, `(name)` is just `name`, and the driver rejects the second. It is the most common typo in this habit and the error message is unhelpful.

---

[← Module 3 home](./README.md)
