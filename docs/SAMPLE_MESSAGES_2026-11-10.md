# 10 November: sample conversations and messages

The project specification asks for about 100 records for each kind of data. The two Messages tables (US62–US64) had none, so the generator now creates them and `sample_demo.db` was rebuilt. Nothing else changed: the project list still shows 12 projects per page.

## Results

| Check | Result |
|---|---|
| New checks written before the change (`tests/test_sample_conversations.py`) | 7 failed, 3 passed (`sample-messages-2026-11-10-evidence/new-tests-red.xml`) |
| Same 10 checks after the change | 10 passed (`new-tests-green.xml`) |
| Full suite | 484 passed (`final-results.xml`) |
| Older sample data | Every other table has the same rows as before (100 profiles, 282 accounts, 110 companies, 120 categories, 320 projects, 1,093 views, 576 saves). Only the dates moved, because the generator dates everything relative to the day it runs. |

## What the generator adds

| Table | Records | Notes |
|---|---|---|
| `consultations` | 150 | 74 New, 54 Replied, 22 Closed. Each joins an active customer to the designer who owns the project. One conversation per customer and project. |
| `consultation_messages` | 450 | 1 to 6 messages per conversation. The customer writes first, then the two take turns. Each conversation follows one of eight short scripts (cost, timeline, materials, site visit and so on), so it reads sensibly. |

- Some conversations are unread on each side, so the Messages numbers have something to show.
- The same seed gives the same conversations on every computer.
- `--conversations N` changes how many are created (default 150).

## Demo logins

| Login | What Messages shows |
|---|---|
| `designer@demo.com` | 8 enquiries: 4 New (3 unread, so the number is 3), 3 Replied, 1 Closed |
| `customer@demo.com` | 3 conversations: Designer Replied (unread, so the number is 1), Waiting for Reply, Closed |

The two demo logins share one conversation, on the demo designer's last project. The demo designer's first project ("Industrial Bedroom - Shophouse, Clementi") has no conversation from the demo customer, so Contact Designer can be shown live from the start.

## Code

Only `scripts/generate_test_data.py` changed: `CONVERSATION_SCRIPTS`, `conversation_lines()`, `plan_conversation()` and `add_conversations()`, each with a comment above it. Conversations are generated last, so every earlier random value is the same as before.
