# Renofolio: interior design project matching platform

**8 November 2026 update.** The platform is now called Renofolio. This release fixes the 8 November review: Title Case wording, the eight bugs (including the new US60/US61 Reactivate stories and "Based on" staff profiles), the confusing-behaviour list and the sample-data text. Every function now has a short comment above it explaining what it does. Details, test evidence and the design-document updates are in [8 November changes](docs/FEEDBACK_2026-11-08.md).

本版平台改名为 Renofolio，修正了 11 月 8 日审查里的所有问题，并在每个函数上方加了简短注释。详情、测试记录和需要更新的设计文档内容见 [8 November changes](docs/FEEDBACK_2026-11-08.md)。

Earlier work:

- US42–US59: [US42–US59 handover](docs/US42-US59_HANDOVER.md).
- Designer v3 work and feedback: [US23–US41 handover](docs/US23-US41_HANDOVER.md) and [v3 feedback](docs/FEEDBACK_2026-11-06.md).
- Customer work: [US01–US22 handover](docs/US01-US22_HANDOVER.md) and [preview and filter update](docs/PREVIEW_FILTERS_UPDATE.md).

## Run locally on Windows

Use Python 3.11 or newer. The deployment uses Python 3.12.

Open **Command Prompt (cmd)** in the extracted folder that contains `run.py` (if the zip made a folder inside a folder, go into the inner one). Type these three lines one at a time:

```bat
py -m pip install -r requirements.txt
set IDP_DB_PATH=%cd%\sample_demo.db
py run.py
```

Open <http://127.0.0.1:5000> and keep the window open. Press Ctrl+C to stop the server. Next time, only the last two lines are needed.

The first start creates a file called `.renofolio_secret_key` next to the database. It keeps you logged in when the app restarts. Do not share it or upload it; it is already excluded from Git.

**Upgrading an existing database (6 November):** on start-up the app upgrades an older database in place: `company_information` becomes `companies` (phone/email become contact number/contact email) and project views/favourites are set to be deleted with their project. Every row is kept. Copy your database file first if you want a backup.

**升级现有数据库：** 启动时会自动升级旧数据库，所有数据保留。如需备份，请先复制数据库文件。

新版 ZIP 已包含带预览图的 `sample_demo.db`，可以直接启动。

To add photos to an existing database without resetting it:

```bat
py scripts\add_sample_photos.py --db sample_demo.db
```

The photo updater makes a database backup, fills only empty photo URLs and can be run again safely. To deliberately rebuild disposable demo data, run `py scripts\generate_test_data.py --db sample_demo.db`; this generator replaces the selected database.

Demo passwords are all `Password123`:

| Role | Email | Login page |
|---|---|---|
| Customer | customer@demo.com | /customer/login |
| Interior Designer | designer@demo.com | /designer/login |
| User Admin | admin@demo.com | /admin/login |
| Platform Manager | manager@demo.com | /pm/login |

The generator creates 100 profiles, 282 accounts, 110 companies, 120 categories, 320 projects, linked views and saves, and 150 conversations with 450 messages. Some accounts are deliberately suspended. Staff accounts `admin06`–`admin10` and `manager06`–`manager10` use custom team profiles (for example "Support Team 01", based on User Admin), so those profiles have real users.

The demo includes eight project-specific AI-generated illustrations. Six cover the first Find My Style results for Dining Room, S$60,000, Japandi and Completed Projects. Two cover the Coastal and Mid-Century Modern home offices on the first Browse Projects page. The other fictional projects use one of six local room-type illustrations. The shipped database and the default data generator use the same preview assignments. Generation prompts are in `app/static/sample-projects/generation-prompts.json`.

## Tests

```bat
py -m pip install pytest pytest-cov
py -m pytest -q
py -m pytest --cov=app --cov-report=term-missing
```

Tests create separate temporary databases. On 9 November the full suite passed 426 tests, and 18 browser checks passed. The records are in [8 November changes](docs/FEEDBACK_2026-11-08.md).

测试使用独立的临时数据库。交接说明包含逐项验收表、修改内容和实际结果。

## Customer features

| Stories | Features |
|---|---|
| US01-US12 | Customer/designer registration, four role logins/logouts, own details and updates |
| US13-US17 | Browse, keyword search and category, status and budget filters (S$0 to S$10,000,000). Each page shows up to 12 projects, with page numbers and Go to Page. Back from a project restores the page and filters. |
| US18 | Project details, one view record per successful opening |
| US19-US21 | Save once (stays on the project page and shows the message), view own favourites (saved projects hidden by a suspended designer are counted, not lost), search own favourites |
| US22 | Confirm/cancel removal; keep save/removal timestamps; allow later re-saving |
| US32-US33 | Designer name on a project opens the designer's portfolio (Current and Past groups); Company Information button opens the company page with Back to Portfolio |

## Interior Designer features

| Stories | Features |
|---|---|
| US23-US25 | Create, view and edit company information. Company name, contact email and contact number are required; one record per designer |
| US26 | Create a project with an uploaded photo (JPG/PNG/WebP, up to 5 MB) and a budget of S$0 to S$10,000,000; company information must be added first |
| US27-US28, US31 | My Interior Design Projects as cards; one filter box like Browse IDPs (Keyword, Status, Apply filters, Clear all): each alone or both together; project details with Edit and Delete |
| US29 | Edit a project, including Current to Past; the photo is kept unless a new one is chosen |
| US30 | Delete after a warning: the project, its views and its favourites are deleted together in one transaction |
| US34-US35 | Project Statistics: choose a project, then View Count or Shortlist Count |
| US36-US38 | Project Interest Summary with Sort by Views / Sort by Shortlists (ties listed by title) |
| US39-US40 | Statistics for a Period: day, week (Monday to Sunday) or month around a chosen date; views or new saves per project |
| US41 | Portfolio Totals: total views and current shortlists, equal to the summary's sums |

Designer controllers use the shared access guard, so they check the session, account/profile status and the Interior Designer role themselves, and every query is limited to the designer's own records.

Search is case insensitive for the English catalogue and treats `%` and `_` as literal keyword characters. Budget bounds are inclusive and must be finite, non-negative numbers. All provided criteria combine with AND; blank criteria are unrestricted. A budget filter requires both bounds. Applying changed criteria resets the page to one; pagination retains the filters. Clear all returns to the full list.

Customer identity comes from the persisted session. The route guard checks role/status before rendering protected pages. Personal-details, project-detail and favourites Controllers repeat that check before returning private data or making changes. Project visibility consistently requires an active designer account and profile. Removing a favourite preserves its history.

## User Admin and Platform Manager features

| Stories | Features |
|---|---|
| US42–US46 | Create active staff accounts with an email, password, contact number and any active staff profile. View, update and suspend accounts. Search by name/email and profile, 20 rows per page. |
| US47–US51 | Create profiles "Based on" User Admin or Platform Manager, search by name or description, view the account count, edit the description and suspend custom profiles (the four built-in profiles and your own profile are protected). |
| US60–US61 | Reactivate a suspended account or profile after confirming (new stories, 8 November). |
| US52–US56 | List categories with customer-visible project counts, 20 per page. Create, edit, search and confirm removal of unused categories. |
| US57–US59 | Generate daily, weekly and monthly reports with new accounts, new projects, project views and new saves. |

## Code and design

```text
app/boundary/       Pages, forms, route mapping and response rendering
app/control/        Request validation, permissions and business flow
app/entity/         SQLite persistence and records
app/common/         Request objects, Result, validation and clock
app/templates/      Role pages and forms
tests/              Acceptance and regression tests for US01–US61
docs/               Story traceability, design alignment notes and test evidence
```

Boundary classes call Controllers rather than querying the database. Names were retained from the supplied code where they consolidate shared behaviour; the handover lists the diagram-to-code differences for the design team. The original Word documents are not modified.

## TDD and deployment evidence

The US42–US59 checks were run on the received v3 code before the application changes. See `docs/us42-us59-evidence/red.xml` and `green.xml` for the recorded before and after results. The earlier handovers retain the evidence for their own changes.

本次保留真实的先失败、后修正、再通过记录。不能把已经写好的旧代码拆成两个提交来声称原本采用了 TDD。

The 8 November changes followed the same order: 55 new checks were committed first (53 failed, 2 passed), then the fixes (all 55 pass). See `docs/feedback-2026-11-08-evidence/`.

This release was verified on local Flask and SQLite. GitHub Actions and Render configuration are included for the team's deployment work. Fonts are served from `app/static/fonts` (SIL Open Font License), so the app looks the same without internet.
