Historical snapshot from 2 November 2026. Combined filtering and generated previews were added on 3 November; see PREVIEW_FILTERS_UPDATE.md for current behaviour.

# CSIT314 US01 to US22 verification and handover

Date: 2 November 2026

The supplied US01-US12 account and login functions have been checked, and the existing US13-US22 browsing/favourites implementation has been completed and corrected against the supplied designs. The final application passes 226 automated tests and 16 Chrome workflow checks.

队友的 US01-US12 已验证；US13-US22 已按你后补的设计文档核对并修正。本次是在队友 ZIP 的基础上继续，原 ZIP 里已存在的功能不应全部计为本次新增代码。

## Scope and references

- `SoftwareAss.docx`: user stories, use case descriptions, embedded B-C-E/sequence diagrams and persistence design for US01-US12.
- `SoftwareAss (1).docx`: the corresponding designs for US13-US22. This document replaced the initial provisional ZIP-only story mapping as the source for those stories.
- The supplied `idp-platform.zip`: the implementation baseline. Input hashes are recorded in `evidence/input-provenance.json`; all three supplied files remain unchanged.

The deliverable includes the inherited US23-US59 code so that the application still runs as a whole. Passing its inherited tests is regression evidence, not acceptance against those stories' unfinished designs. No online deployment or original Git/TDD history is claimed.

## Verified results

| Check | Actual result |
|---|---|
| Unchanged incoming implementation | 140 passed in 148.60 seconds |
| First 84 additional acceptance checks, before fixes | 35 failed, 49 passed |
| Same first 84 checks, after fixes | 84 passed in 45.60 seconds |
| Final suite including new document-alignment checks | 226 passed in 204.87 seconds |
| New acceptance/regression cases in final suite | 86 |
| Whole-app Python statement coverage | 91.66% (2285/2493) |
| Real browser | Chrome 156.0.8078.79; 16 workflow checks passed; no page JavaScript errors |
| Layout checks | 1440-pixel desktop and 390-pixel mobile viewport; project, favourite and detail screenshots inspected |
| Local request timing | 3 samples for each of 22 stories; slowest 621.4 ms, all below 2 seconds |

The timing check measured individual Flask test-client requests against 320 projects and 291 accounts. It includes server-side hashing/database/rendering where applicable. It is a local, sequential check, not a public-network or concurrent-load guarantee. Browser workflow durations include navigation, typing, screenshots and multiple requests; they are not individual response-time measurements.

测试不是全部独立的 unit tests：其中包括 Controller + SQLite 测试、Flask HTTP 测试，以及另外执行的真实浏览器流程。覆盖率衡量执行过的代码行，不能直接当作“所有需求完成率”。

## Changes that matter

1. **Empty project results now display their message.** The template used `result.data.items`, which resolved to a dictionary method. It now reads the actual list key, so browse/search/category/status/budget empty states work.
2. **US15 retains the full project list when a category disappears.** It shows the category error and returns to the first full-list page, as UC15 A1 requires. Ordinary category matches still use their filtered pagination.
3. **Budgets reject infinity and numeric overflow.** `inf` and `1e309` no longer count as valid budget bounds. Existing inclusive bounds and reversed-range errors remain.
4. **Customer Controllers enforce permissions themselves.** Personal details, detail views and favourites use the shared access guard before returning private information or writing data. Wrong-role and suspended sessions cannot bypass checks by calling a Controller directly. Existing HTTP route guards remain.
5. **Logout deletes expired session rows too.** Active, expired and unknown tokens all lead safely to the login page. Protected responses include `Cache-Control: no-store, private`; logout followed by browser Back was checked in Chrome.
6. **Project availability is consistent.** Browsing, detail views, saving and favourite lists require a non-removed project belonging to an active designer account/profile. The earlier implementation could hide a suspended designer's project from browsing while still saving or listing it in favourites. Hiding unavailable projects preserves their favourite/history rows; it does not delete history.
7. **Keyword searches match literal text.** `%`, `_` and the escape character are escaped before SQL LIKE matching. Queries remain parameterized. Favourite search also uses a 100-character limit and deterministic ordering for equal timestamps.
8. **Favourites follow the supplied customer UI.** Saved projects use the team's existing card style, with saved dates and removal actions. Remove opens confirmation; Cancel changes nothing; confirming sets `removed_at` while retaining `saved_at`.

主要修复包含空列表提示、失效分类后的列表保留、预算验证、权限检查、过期登出和收藏流程。没有重做队友的整个前端，也没有把原本已有的 US13-US22 实现冒称为从零新增。

## Story acceptance

The CSV beside this report provides routes, Controller names and test references for each row.

| Story | Feature | Behaviour checked | Result |
|---|---|---|---|
| US01 | Create Customer Account | Registration: valid/invalid input, salted hashes, duplicate email; form values retained without password | Pass |
| US02 | Customer Login | Normal/empty/unknown/wrong password/suspended account/suspended profile/wrong role; sliding timeout | Pass |
| US03 | View Personal Details | Own details only; no password hash; expired/wrong-role/suspended sessions denied | Pass |
| US04 | Update Personal Details | Own name/contact updated; email immutable; invalid data does not save; forged account ID ignored | Pass |
| US05 | Customer Logout | POST logout removes server token; expired logout succeeds; protected pages/Back require login | Pass |
| US06 | Create Designer Account | Same registration rules as US01; creates designer role; no staff registration route | Pass |
| US07 | Designer Login | Full login alternative-flow matrix; designer home; sliding timeout | Pass |
| US08 | Designer Logout | Deletes active/expired token; redirects to designer login | Pass |
| US09 | User Admin Login | Full login alternative-flow matrix; only active admin account/profile accepted | Pass |
| US10 | User Admin Logout | Deletes active/expired token; redirects to admin login | Pass |
| US11 | Platform Manager Login | Full login alternative-flow matrix; only active manager account/profile accepted | Pass |
| US12 | Platform Manager Logout | Deletes active/expired token; redirects to manager login | Pass |
| US13 | Browse IDPs | 10 per page; total count; stable pagination; invalid page; visible empty state; removed projects omitted | Pass |
| US14 | Search IDPs by Keyword | Title/description matching; English case-insensitivity; blank/no matches; literal wildcard characters; paged results | Pass |
| US15 | Filter IDPs by Category | Live category list; only category matches; no matches; deleted category error retains full list | Pass |
| US16 | Filter IDPs by Status | Current/Past only; case-normalized; invalid status; visible empty state; pagination | Pass |
| US17 | Filter IDPs by Budget | Inclusive range; both finite and non-negative; reversed/blank/non-numeric/infinite rejected; pagination | Pass |
| US18 | View IDP Details | Details shown; exactly one view per successful opening; invalid/deleted/unavailable/expired cases record no view | Pass |
| US19 | Save IDP to Favourites | Own session identity; one current save; duplicate feedback; unavailable/expired denied; timestamp recorded | Pass |
| US20 | View Favourites | Only own current saves; newest first; cards/date/removal action; empty list and browse link | Pass |
| US21 | Search Favourites | Search only own current favourites by title/description; English case-insensitivity; blank/no matches; expired denied | Pass |
| US22 | Remove IDP from Favourites | Confirmation and Cancel; only own records; already removed; expired denied; retain saved_at and set removed_at; re-save allowed | Pass |

## Design alignment for the design team

The functions are verified; the supplied diagrams are not literal descriptions of every implementation name. Synchronize the final diagrams with the agreed implementation before submitting the report. These are the concrete differences to review:

| Design wording | Current implementation | Design action |
|---|---|---|
| Role-specific `openCustomerHomePage` / `openDesignerHomePage` and similar methods | Shared inherited `_LoginPage.openHomePage()` with each role's `home_endpoint` | Show the shared base method or agree a consistent naming convention |
| `ViewDetailsRequest`, `LogoutRequest`, `ViewFavouritesRequest` | Shared `SessionRequest` | Use the shared DTO in diagrams or explicitly model the specialization |
| Detail-read `IDPRequest` | `IDPIdRequest`; the existing `IDPRequest` is used for designer project editing | Keep distinct read/edit request names to avoid a collision |
| `SaveFavouriteRequest`, `RemoveFavouriteRequest` | `FavouriteRequest`, including the confirmation flag | Show the shared request or agree separate types |
| `selectViewPersonalDetails`, `submitUpdatedDetails`, `clickLogout` | `requestDetails`, `submitUpdate`, `logout` | Update Boundary operation labels to match routes and code |
| Filter `submitFilter`, detail `submitSave`, favourites `requestList` | `applyFilter`, `saveToFavourites`, `requestFavourites` | Update the Boundary calls in the sequence/class diagrams |
| Customer private operations call `Sessions.getAccountId` directly | They call `AccessGuardController`, which checks session/account/profile/role and returns the account ID | Add the shared guard dependency; place access checking before private reads or writes |
| US18 diagram loads the project before resolving the Customer | Implementation authorizes before the project lookup and view insertion | Keep this authorization order in the final sequence |
| US15 error handling is summarized in the sequence diagram | `CATEGORY_NOT_FOUND` triggers full-list retrieval in the Boundary | Add the UC15 A1 branch to the final sequence |
| US01-US12 relational model omits several shared account/profile columns | Existing merged schema includes `username`, `role_code`, timestamps and extra metadata | Coordinate one schema with the other members; this handover does not perform a destructive schema migration |
| US13-US22 project model omits update/removal metadata | Existing code has `updated_at` and `removed_at` to support unavailable projects/history | Include these fields if retaining the existing soft-delete design |

The active-designer visibility rule, 100-character search limit and literal wildcard handling are explicit implementation decisions that support consistent availability and keyword behaviour; the supplied use cases do not specify every one of these edge cases. Keep these decisions in the agreed acceptance criteria. Filters are independent, as shown by the individual use cases; combined multi-filter search was not added.

给 Design 组的任务是同步这些具体差异。不能只凭类名相近就声称图与代码完全一致，也不必照搬图中所有重复的辅助方法。

## Genuine evidence and contribution

`evidence/new-tests-red.xml` records the new checks failing against the incoming implementation before application edits. `evidence/first-fixes-green.xml` records the first corrections passing. The later design checks and final suite are recorded separately. This supports the fixes performed in this handover; it does not establish TDD for the teammate's original implementation, and no artificial Git history was created.

Keep the teammate's original work attributable to them. Review `US01-US22_changes.patch` to identify the actual code changes, and use the acceptance tests, bug fixes, integration verification and explanation you can demonstrate as evidence of your own participation. Do not claim all inherited features as new work.

## Run and demonstrate

Follow the Windows setup commands in the root README. Use the generated demo database, then demonstrate:

1. Register or log in as a Customer; view/update personal details; reject invalid details.
2. Browse ten projects per page, go to the next page, search and clear a keyword, apply each filter, and show empty/error states.
3. Open a project and explain the single new `project_views` record.
4. Save a project, show that it cannot be saved twice, search favourites, and show that another Customer has a separate list.
5. Cancel removal, then confirm removal; explain the retained save/removal timestamps and re-save behaviour.
6. Log out and show protected pages require login. Show the other three roles' login/logout entry points.

The ZIP excludes the supplied database and Python caches. Generate a fresh demo database after extraction. If the teammate has made newer changes since the supplied ZIP, merge the patch into that version rather than replacing their newer folder wholesale.

This is a local functional handover for US01-US22. The inherited CI/Render configuration and US23-US59 design acceptance remain separate team work.
