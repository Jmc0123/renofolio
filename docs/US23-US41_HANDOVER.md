# CSIT314 US23 to US41 verification and handover

Date: 6 November 2026. Later the same day, three issues found in testing were fixed; see `FEEDBACK_2026-11-06.md`. The figures below are from the earlier handover; after the fixes the suite has 323 passing tests, and US26's message is "Project created successfully."

US23-US41 (Interior Designer company information, portfolio management and interest statistics, plus the Customer's view of a designer) were checked against the updated `SoftwareAss.docx` and corrected to match it. Work started from `idp-platform-us22-preview-filters-2026-11-03.zip`. The final application passes 315 automated tests and 13 browser workflow checks.

按更新后的 `SoftwareAss.docx` 核对并修正了 US23-US41。本次以 11 月 3 日的 ZIP 为基础继续，原 ZIP 中已有的 US23-US41 代码是本次修改的起点，不应全部计为本次新增。

## Scope and references

- `SoftwareAss.docx` (6 November version): user stories, use case descriptions, task lists, B-C-E class diagrams, sequence diagrams, UI wireframes and the two relational models for US23-US31 and US32-US41.
- `idp-platform-us22-preview-filters-2026-11-03.zip`: the implementation baseline (263 passing tests).
- The team note asking for US30 to delete project, view and favourite rows in one transaction, and US37/US38 to order equal counts by project title.

US42-US59 were not changed except where they share code (see "Effects outside US23-US41").

## Verified results

| Check | Actual result |
|---|---|
| New US23-US41 acceptance checks against the unchanged 3 November code | 81 checks: 55 failed, 25 errors (fixtures needing missing names), 1 passed |
| Same checks after the changes | 81 passed |
| Final suite | 315 passed in 40.9 seconds (`us23-us41-evidence/final-results.xml`) |
| Whole-app Python line coverage | 90.58% (2674/2952) |
| Real browser (Chromium via Playwright) | 13 of 13 workflow checks passed; no page JavaScript errors |
| Layout | 1440-pixel desktop and 390-pixel mobile; no horizontal scrolling on the designer list and statistics pages |
| Local request timing | 3 samples for each of 20 US23-US41 requests on the full test data; slowest 6.2 ms |
| Environment | Python 3.13.18, Flask 3.1.3, Werkzeug 3.1.9, pytest 8.3.5 (pinned `requirements.txt`) |

The suite count changed from 263 to 315: the 30 cases in the old `tests/test_us23_us41_designer.py` were retired (they asserted the previous names and the old soft delete; every scenario is covered by the new file), and 82 checks were added. The one passing check in the red run was the invalid-designer-ID case, which already worked.

The timing figures are Flask test-client requests on one machine. They are not a network or load test.

测试包括 Controller + SQLite 测试、Flask 页面测试和真实浏览器流程。覆盖率是执行过的代码行比例，不等于需求完成率。

## Changes that matter

1. **US30 deletes for real, in one transaction.** `InteriorDesignProjects.delete()` deletes the project's `project_views`, its `favourites` and the project inside one transaction. A test makes the final delete fail on purpose and confirms the view and favourite rows are still there (rollback). New databases also have `ON DELETE CASCADE` on both child tables, as in the relational model. The confirmation dialog warns that views and favourites are deleted too; Cancel changes nothing. An uploaded photo file is removed with its project.
2. **US37/US38 order equal counts by title.** Sorting is by count (highest first), then title, then project ID.
3. **`Companies` entity and `companies` table replace `CompanyInformation`/`company_information`.** Contact email and contact number are now required and validated, as US23 step 3 states. `hasCompany()` is checked before `create()`; the UNIQUE designer_id remains as a backstop.
4. **Names now follow the diagrams.** Controllers: `FilterMyIDPsController`, `SortByViewCountController`, `SortByShortlistCountController`, `ViewPeriodViewsController`, `ViewPeriodSavesController`. Requests: `CompanyInfoRequest`, `UpdateCompanyInfoRequest`, `ViewCompanyInfoRequest`, `CreateIDPRequest`, `UpdateIDPRequest`, `ViewMyIDPsRequest`, `FilterMyIDPsRequest`, `DeleteIDPRequest`, `SearchMyIDPsRequest`, `DesignerIdRequest`, `ProjectStatRequest`, `InterestSummaryRequest`, `PeriodStatRequest`, `PortfolioTotalsRequest`. Entity methods: `isOwner`, `findOwned`, `filterMineByStatus`, `searchMine`, `delete`, `countByProject`, `countPerProject`, `countPerProjectBetween`, `countByDesigner`, `countCurrent`, `countCurrentPerProject`, `countSavesPerProjectBetween`, `countCurrentByDesigner`. Controller helper methods: `companyExistsResult`, `notOwnerResult`, `countResult`, `buildSummary`, `sortByViewCount`, `sortByShortlistCount`, `toDateRange`, `buildPeriodReport`, `totalsResult`.
5. **Pages follow the wireframes.** Interior Designer Home has Company Information, My Interior Design Projects and Portfolio Statistics. My projects are cards with a search bar and a Status filter (All/Current/Past, Apply Filter, Clear Filter). Statistics are four pages: Project Interest Summary (sort buttons), Project Statistics (project dropdown, View Count, Shortlist Count), Statistics for a Period (Day/Week/Month, date, Views, New Shortlists) and Portfolio Totals. Customers go from a project's designer name to the portfolio, then to a separate Company Information page with Back to Portfolio.
6. **Create/Edit IDP takes a photo file.** JPG, PNG or WebP up to 5 MB, checked by file content. The Boundary stores it under `app/static/uploads/idp/` and passes only its address to the Controller. Editing keeps the photo unless a new one is chosen.
7. **Designer controllers enforce the role themselves.** They use the shared access guard (session, account/profile status, Interior Designer role), as the Customer controllers already did. A Customer session calling a designer controller directly is refused and saves nothing.
8. **Messages match the use cases**, for example "Company information saved.", "Company information already exists. Use Edit instead.", "You have not added company information yet.", "Project created. Customers can now find it.", "Budget must be 0 or more.", "You have not created any projects yet.", "This project is not available.", "This project is no longer available.", "You have no past projects yet.", "None of your projects match 'rooftop'.", "This designer has no projects yet.", "This designer has not added company information yet.", "Please choose a period and a date.", "You have no projects yet.".
9. **Periods follow the accuracy rule.** A chosen date gives the day (midnight to midnight), the week (Monday to Sunday) or the month (1st to last day). Projects with no activity show 0. US40 counts every successful save in the period, even if removed later.
10. **Existing databases are upgraded in place.** On start-up, `company_information` rows are copied into `companies` (phone and email become contact number and contact email), and `project_views`/`favourites` are rebuilt with the cascade. Every row is kept and running it again changes nothing; a test covers this. The shipped `sample_demo.db` was regenerated.

主要修改：US30 真正删除并在同一事务中删除浏览和收藏记录；US37/US38 同数按标题排序；公司表改为 `companies` 并要求联系邮箱和电话；类名、方法名、页面和提示语按设计文档统一；支持上传项目图片；旧数据库启动时自动升级，数据不丢失。

## Story acceptance

`US23-US41_TRACEABILITY.csv` lists the route, Controller and tests for each row.

| Story | Feature | Behaviour checked | Result |
|---|---|---|---|
| US23 | Create Company Information | Required name/contact email/contact number and formats; one record per designer; expired and Customer sessions save nothing | Pass |
| US24 | View Company Information | All six fields with Edit button; none-yet message with Create button; expired session | Pass |
| US25 | Update Company Information | Updated message; invalid email keeps values and saves nothing; create-first message; only own record; Customers see the change | Pass |
| US26 | Create IDP | Success message; budget/title/category/status rules; photo upload; expired and wrong role save nothing | Pass |
| US27 | View My IDPs | Own projects as cards with count; details with Edit/Delete; none-yet message; not owned/not found | Pass |
| US28 | Filter My IDPs by Status | Current/Past; missing/invalid status; "You have no past projects yet."; Clear Filter | Pass |
| US29 | Update IDP | Current to Past; budget rule; not owned/deleted changes nothing; photo kept | Pass |
| US30 | Delete IDP | Warning; Cancel; project + views + favourites deleted together; rollback; cascade; not owned deletes nothing | Pass |
| US31 | Search My IDPs | Own projects; ignores case; empty keyword; no matches; literal `%` and `_` | Pass |
| US32 | View Designer Portfolio | Current/Past groups; no projects; invalid ID; no view recorded | Pass |
| US33 | View Designer Company Information | Exactly as entered; none-yet message; invalid ID; Back to Portfolio | Pass |
| US34 | View Project View Count | Total views; no project chosen; not owned; 0 when none | Pass |
| US35 | View Current Shortlist Count | Removed favourites excluded; same alternative flows; 0 when none | Pass |
| US36 | View Project Interest Summary | Numbers equal US34/US35; other designers excluded; no projects | Pass |
| US37 | Sort by View Count | Highest first; ties by title | Pass |
| US38 | Sort by Current Shortlist Count | Highest first; ties by title | Pass |
| US39 | Project Views for a Period | Day/week/month boundaries; zeros shown; missing period/date; no projects | Pass |
| US40 | New Shortlists for a Period | Saves later removed still count; boundaries; messages | Pass |
| US41 | Portfolio Totals | Equal to US36 sums; zero with no projects; expired | Pass |

## Design alignment for the design team

The code now uses the diagrams' names. These remaining differences should be reflected in the final diagrams, or agreed as implementation detail:

| Design wording | Current implementation | Design action |
|---|---|---|
| Designer controllers call `Sessions.getAccountId()` | They call the shared `AccessGuardController` (session, status and role), stored in the `sessions` attribute | Show the guard, as already noted for US13-US22 |
| `countPerProject()`, `countCurrentPerProject()`, `countPerProjectBetween()`, `countSavesPerProjectBetween()` return `Result` | They return a `Result` whose data is `{idpId: count}`; `buildSummary()`/`buildPeriodReport()` add 0 for missing projects | Note the map in the class diagrams |
| US39/US40 result order not specified | Highest count first, then title | Add to the use cases or accept as UI detail |
| `companies` columns in the model | Code also has `created_at` | Add `created_at` to the US23-US31 model |
| `interior_design_projects` model has no `updated_at`/`removed_at` | Both columns remain. Nothing sets `removed_at` now; it keeps rows hidden that an older version soft-deleted, in upgraded databases | Add them, or note them as legacy columns |
| Interior Designer Home is `DesignerHomePage` | Home page content is rendered by `DesignerDashboard`; `DesignerHomePage` (US08) handles Log Out | Merge the names in the diagram, or show both |
| US30 Cancel happens in the dialog | `DeleteIDPRequest.confirmed=False` returns `CANCELLED` so the T2 "designer cancels" test is a Controller test | Add the flag to `DeleteIDPRequest` |
| US26 "adds a photo" | The Boundary validates and stores the file and passes `photoUrl` | Show `photoUrl` in `CreateIDPRequest`/`UpdateIDPRequest` |
| `ProjectStatRequest` result | Data holds only the count (`viewCount` or `shortlistCount`), as in the diagram | None |
| Old addresses | `/designer/interest`, `/designer/projects/filter` and `/designer/projects/search` redirect to the new pages | None |

请设计组按上表同步图与代码的差异，不要只因类名相同就声称完全一致。

## Effects outside US23-US41

- **Platform reports (US57-US59, Member 6):** views and favourites of a deleted project are gone, so a report for a past period no longer counts them. This follows the US30 postcondition ("no longer ... in the statistics"), but Member 6 should confirm it is acceptable for their reports.
- **Customer favourites (US20-US22):** a deleted project disappears from Customers' favourites, as US30's postcondition says. Projects hidden because a designer is suspended still keep their favourites and history, as before.
- **Test data:** `generate_test_data.py` writes `companies` and no longer marks about 3% of projects as removed (deleted projects no longer exist). The random sequence is unchanged, so all other generated values are the same as before.

## Genuine evidence and contribution

`us23-us41-evidence/new-tests-red.xml` records the 81 new checks run against the unchanged 3 November code before any application edit. `final-results.xml` and `final-results.log` record the final suite. Two items were added after the red run and are not part of it: the database-upgrade test, and the assertion that deleting a project removes its uploaded photo. One fixture mistake in the new tests (a dictionary key used twice) was corrected during the green step.

The browser run in `browser-results.json` is the third run. The first two failed because of mistakes in the browser script (a selector that matched the hidden Log out button, and one wrongly expected message), not the application.

No Git history was created. Use `US23-US41_changes.patch` (2,022 added and 1,014 removed lines against the 3 November code, excluding images and evidence) to show exactly what changed. Keep teammates' earlier work attributed to them.

## Run and demonstrate

Follow the Windows commands in the root README with `sample_demo.db`. If you are upgrading the Desktop project, copy its database file first; the app upgrades it automatically on start-up and keeps every row. Then demonstrate, as `designer@demo.com`:

1. Interior Designer Home: Company Information, My Interior Design Projects, Portfolio Statistics.
2. Company Information: Edit, enter an invalid contact email (error, values kept), then save.
3. My projects: filter Past, Clear Filter, search "kitchen", then "rooftop" (no matches).
4. Create Project with a negative budget (error), then with a photo; open it; Edit to Past.
5. Delete: show the warning, Cancel, then Delete; explain that its views and favourites are deleted in one transaction.
6. Portfolio Statistics: Interest Summary, Sort by Views and by Shortlists (ties by title); Project Statistics; Statistics for a Period (week); Portfolio Totals equal the summary's sums.
7. As `customer@demo.com`: open a project, click the designer's name, then Company Information and Back to Portfolio.
