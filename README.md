# Renofolio

Renofolio is an interior design project platform built for the CSIT314 group assignment. Customers browse projects, save favourites and contact designers. Designers manage their portfolios and consultations. User Admins manage accounts and profiles, and Platform Managers manage project categories and review platform activity.

The application uses Python, Flask, Jinja and SQLite. Project previews, fonts and browser assets are served locally.

## Getting Started

Use **Python 3.11 or newer**. For a fresh GitHub checkout, run these commands from the folder where you want to keep the project.

```sh
git clone https://github.com/Jmc0123/renofolio.git
cd renofolio
```

If you have the final project ZIP, extract it and enter the folder containing `run.py` and `requirements.txt`. The final ZIP includes `sample_demo.db`. From a fresh GitHub checkout, use the setup commands below to generate it.

### Windows Command Prompt

Run each line separately in the project folder.

```cmd
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
if not exist "sample_demo.db" .venv\Scripts\python.exe scripts\generate_test_data.py --db sample_demo.db
set "IDP_DB_PATH=%CD%\sample_demo.db"
.venv\Scripts\python.exe run.py
```

### macOS and Linux

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
test -f sample_demo.db || .venv/bin/python scripts/generate_test_data.py --db sample_demo.db
IDP_DB_PATH="$PWD/sample_demo.db" .venv/bin/python run.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in a browser. Keep the terminal open while using the site. Press **Ctrl+C** to stop the server.

## Demo Accounts

All four seeded demo accounts use the password `Password123`.

| Role | Email | Login path | Page after login |
|---|---|---|---|
| Customer | `customer@demo.com` | `/customer/login` | Customer Home |
| Interior Designer | `designer@demo.com` | `/designer/login` | Interior Designer Home |
| User Admin | `admin@demo.com` | `/admin/login` | User Accounts |
| Platform Manager | `manager@demo.com` | `/pm/login` | Project Categories |

## Features and User Stories

| Stories | Area | Implemented workflows |
|---|---|---|
| US01–US12 | Accounts and authentication | Customer and designer registration, role-specific login and logout, and viewing or updating customer details. |
| US13–US22 | Customer projects and favourites | Browse up to 12 projects per page, combine keyword, category, status and budget filters, view details, save projects, and search or remove favourites. Project details link back to the previous filters and page. |
| US23–US31 | Designer company and projects | Manage company details and create, edit, search, filter and delete owned projects. Company details are required before creating a project. An optional JPG, PNG or WebP preview may be up to 5 MB. |
| US32–US41 | Portfolios and interest tracking | Customers view designer portfolios and company information. Designers sort project interest summaries, track views and new saves by period, and view portfolio totals and current shortlists. |
| US42–US51 | User administration | Create staff accounts, search accounts and profiles, edit account details and profile descriptions, and suspend eligible accounts or profiles. Custom staff profiles are based on User Admin or Platform Manager. |
| US52–US59 | Platform management | Manage project categories and generate daily, weekly or monthly reports for new accounts, new projects, project views and new saves. Weekly reports use the week containing the selected date. |
| US60–US61 | Reactivation | Restore suspended accounts and profiles. Both the account and its assigned profile must be active for login. |
| US62–US64 | Project consultations | Customers contact designers from project details. Both participants can view their conversation history and reply. Designers can close conversations. A new reply reopens an available closed conversation. |
| US65 | Find My Style | Match a room and budget, then rank projects by selected style and status preferences. Results explain the match, show alternatives within budget and retain the questionnaire answers when the customer returns from a project. |

The customer budget filter takes both a minimum and a maximum when used. Budgets run from **S$0 to S$10,000,000**, with values rounded to cents. Current shortlist counts reflect favourites still saved, while new-save reports count successful save actions during the chosen period.

## Demo Walkthrough

1. Sign in as the **Customer** and open **Find My Style**. Select **Dining Room**, enter **S$60,000**, then choose **Japandi** and **Completed Projects**. Compare **Best Matches** and **Other Options Within Budget**. Use **Show More** to display additional results.
2. Open **Japandi Dining Room - Condominium, Clementi**. Its listed budget is **S$57,000**, which is **S$3,000 below the selected budget**. Select **Contact Designer** and send an enquiry.
3. In a separate browser session, sign in as the **Interior Designer**. Open **Messages**, select the enquiry and reply. The unread number on the Messages entry counts conversations with unread messages. The inbox shows the unread message count for each conversation.
4. Return to the Customer session and refresh the conversation to see the reply. The designer can close it and either participant can send a new reply to reopen it while the project remains available. Choose **Back to My Matches** to return to the same search.
5. Sign in as **User Admin** to show account and profile management. Then sign in as **Platform Manager** to show the category list and generate a report from **Reports**.

The demo Customer and Designer already share a conversation for **Coastal Bathroom - Cluster House, Jurong East**. A fresh demo database leaves the featured Japandi project available for a live first enquiry.

## Sample Data and Storage

The default [sample data generator](scripts/generate_test_data.py) creates fictional records for the demo.

| Data | Records |
|---|---:|
| User profiles | 100 |
| User accounts | 282 |
| Companies | 110 |
| Project categories | 120 |
| Interior design projects | 320 |
| Project views | 1,093 |
| Favourites and save history | 576 |
| Consultation conversations | 150 |
| Consultation messages | 450 |

The demo includes read and unread conversations in New, Replied and Closed states. Eight selected projects have [AI-generated previews](app/static/sample-projects/generation-prompts.json). Other sample projects use room-type illustrations. The bundled [Fraunces](app/static/fonts/OFL-Fraunces.txt) and [Inter](app/static/fonts/OFL-Inter.txt) fonts include their SIL Open Font License files.

**Keep a separate file for any data you want to retain.** The generator replaces the database at the path passed to `--db`. The setup commands above generate `sample_demo.db` only when it is missing. To get the latest seeded conversations while retaining an older demo database, generate a new file such as `sample_messages_demo.db` and set `IDP_DB_PATH` to that file.

The application creates or upgrades its SQLite schema on startup. The [photo updater](scripts/add_sample_photos.py) can fill missing previews in an existing database and backs it up before changing it. SQLite databases, local uploads and the generated session key are kept outside Git.

| Setting | Default and purpose |
|---|---|
| `IDP_DB_PATH` | Selects the SQLite database. The default is `idp_platform.db` in the project root. |
| `HOST` and `PORT` | The local server binds to `127.0.0.1:5000` by default. |
| `SECRET_KEY` | Sets the Flask session signing key. By default the application creates `.renofolio_secret_key` next to the database. |

## Architecture

Renofolio uses a **Boundary–Control–Entity** structure. A request enters a Flask route and Boundary, the Controller checks access and applies the workflow rules, and Entity classes handle SQLite queries and persistence.

| Folder | Responsibility |
|---|---|
| [`app/boundary/`](app/boundary/) | Routes, page boundaries, form input and responses. |
| [`app/control/`](app/control/) | Request validation, permissions and business workflows. |
| [`app/entity/`](app/entity/) | SQLite schema, migrations and data access. |
| [`app/common/`](app/common/) | Request types, result objects and shared validation. |
| [`app/templates/`](app/templates/) and [`app/static/`](app/static/) | Jinja views, styles, scripts and local assets. |
| [`scripts/`](scripts/), [`tests/`](tests/) and [`docs/`](docs/) | Demo setup, automated tests and implementation handovers. |

## Testing and CI

Run the test suite from the project root. The tests use temporary databases.

```cmd
.venv\Scripts\python.exe -m pytest -q
```

For a coverage report, run `.venv\Scripts\python.exe -m pytest --cov=app --cov-report=term-missing`. On macOS and Linux, use `.venv/bin/python` in place of the Windows interpreter path.

The **10 November 2026 release passed 484 automated tests**. The [CI workflow](.github/workflows/ci.yml) runs the suite and checks sample-data generation on pushes and pull requests. It uploads the test report as a workflow artifact.

The [Render configuration](render.yaml) builds the demo database and starts the app with Gunicorn. After tests pass on a push to `main`, the workflow triggers a Render deployment when `RENDER_DEPLOY_HOOK_URL` is configured as a repository secret.

### Known Demo Limitations

- Use the default data generator settings for the counts above. The fixed demo conversations can exceed a small requested conversation count, and a very small project count can cause seeding to fail.
- Two participants opening the same conversation at the same time can occasionally hit a SQLite database lock. A stale first-message form that repeats the last message of a closed conversation can show a success message while leaving that conversation closed.

## Handover Notes

- **US01–US22** [Accounts and customer workflows](docs/US01-US22_HANDOVER.md) and [story traceability](docs/US01-US22_TRACEABILITY.csv).
- **US23–US41** [Designer workflows](docs/US23-US41_HANDOVER.md) and [story traceability](docs/US23-US41_TRACEABILITY.csv).
- **US42–US61** [User Admin and Platform Manager workflows](docs/US42-US59_HANDOVER.md) and [profile and reactivation changes](docs/FEEDBACK_2026-11-08.md).
- **US62–US65** [Consultations and Find My Style](docs/US62-US65_HANDOVER.md), [message fixes](docs/MESSAGES_2026-11-09.md) and [sample conversations](docs/SAMPLE_MESSAGES_2026-11-10.md).

The final ZIP includes the archived test evidence for the group submission. Check [GitHub Actions](https://github.com/Jmc0123/renofolio/actions) for the results of a particular repository run.
