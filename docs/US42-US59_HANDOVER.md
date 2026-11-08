# DesignMatch US42–US59 handover

6 November 2026

The release builds on `idp-platform-us41-designer-2026-11-06-v3.zip` and completes the User Admin and Platform Manager flows against the use cases in `SoftwareAss (2).docx`. The supplied v3 and the design document are the source references. The original v3 implementation and evidence remain attributed to the teammate.

## Designer handover review

| Stories | v3 implementation reviewed | Result |
|---|---|---|
| US23–US25 | One company record per designer with validated contact fields, private editing and shared customer display | The v3 tests passed. A separate HTTP flow confirmed that a company edit appears on the customer company page. |
| US26–US31 | Project photo uploads, own-project listing and editing, combined keyword/status filtering and confirmed deletion | The separate flow verified upload and ownership checks. Confirmed deletion removed the project, views and favourites together. |
| US32–US33 | Designer portfolio grouped by status and company details | Opening the portfolio and company pages recorded no extra project view. |
| US34–US41 | Per-project counts, combined summary, sorting by title for equal counts, date ranges and portfolio totals | Independent checks verified ties, view events, current versus historical saves and the effect of project deletion. |
| US13–US19 feedback | Page numbers, Go to page, Back retaining the list position and saving on the details page | The HTTP audit and Chrome checks confirmed the combined filters, retained page and in-place save. |

All 337 tests in the received v3 passed. The independent audit recorded eight workflow checks on a copy of its sample data. It also reproduced three defects that this release corrects. Project editing now retains its stored photo unless a new file is uploaded. The detail page title contains only the title text. Out-of-range dates produce a validation result in the shared calendar helper.

The v3 combined Designer filter is a useful extension. UC28 and UC31 describe separate controls and missing-input errors. The combined form uses a blank field to leave that criterion unrestricted, while the individual Controllers still validate their required inputs. The design team should show the combined form and retained list position when updating the diagrams.

## Story and code map

English comments marked with story IDs explain decisions in the files below. Boundary classes render forms and call Controllers. The shared route guard checks the persisted session, account status, profile status and role before the request reaches a staff page. Controllers validate the allowed fields and Entities handle SQLite reads and writes.

| Story | Behaviour verified | Main code |
|---|---|---|
| US42 Create User Account | Full name, email, initial password and contact number are required. Only active User Admin and Platform Manager profiles are eligible. Unique emails and salted password hashes are enforced. | `CreateUserAccountController` and `UserAccounts.create()` |
| US43 View User Account | Account details include contact, profile, status and creation time. The presentation data omits the hash. | `ViewUserAccountController` and `UserAccounts.find()` |
| US44 Update User Account | Edit name, email and contact together. Login uses the updated email. The stored profile and password are retained. | `UpdateUserAccountController` and `UserAccounts.update()` |
| US45 Suspend User Account | Confirm suspension, protect the acting admin's own account and revoke the target's sessions in the same transaction. | `SuspendUserAccountController` and `UserAccounts.suspend()` |
| US46 Search User Accounts | Name or email substring combined with an optional profile. Blank submissions show an error. The count covers all matching accounts. | `SearchUserAccountController` and `UserAccounts.search()` |
| US47 Create User Profile | Create an active profile with a unique role name. The Entity assigns its internal role code. | `CreateUserProfileController` and `UserProfiles.create()` |
| US48 View User Profile | Show role, description, status and linked account count. The linked account search returns the same total. | `ViewUserProfileController` and `UserProfiles.find()` |
| US49 Update User Profile | Validate and save the description. The role name is read-only. | `UpdateUserProfileController` and `UserProfiles.update()` |
| US50 Suspend User Profile | Protect the built-in User Admin profile. Suspend eligible profiles and revoke all of their accounts' sessions together. | `SuspendUserProfileController` and `UserProfiles.suspend()` |
| US51 Search User Profiles | Search role names and descriptions. Show the result count and an error for an empty submission. | `SearchUserProfileController` and `UserProfiles.search()` |
| US52 View Project Categories | Sort by name and count the projects that are visible under the corresponding customer filter. | `ViewCategoriesController` and `ProjectCategories.listAll()` |
| US53 Create Project Category | Accept names from 1 to 50 characters and reject duplicate names regardless of English letter case. | `CreateCategoryController` and `ProjectCategories.create()` |
| US54 Update Project Category | Rename while retaining the category ID, so linked projects show the new name. | `UpdateCategoryController` and `ProjectCategories.update()` |
| US55 Remove Project Category | Confirm and remove a category only when no project references it. Hidden and legacy project rows still protect the category. | `RemoveCategoryController` and `ProjectCategories.remove()` |
| US56 Search Project Categories | Literal name substring search, ignoring English letter case. | `SearchCategoriesController` and `ProjectCategories.search()` |
| US57 Generate Daily Report | Count events from midnight to the next midnight. | `GenerateDailyReportController` and `PlatformReports.generate()` |
| US58 Generate Weekly Report | Use Monday through Sunday for the week containing the selected date. | `GenerateWeeklyReportController` and `PlatformReports.generate()` |
| US59 Generate Monthly Report | Count from the first day of the selected month to the first day of the following month. | `GenerateMonthlyReportController` and `PlatformReports.generate()` |

The Admin workflow is in `app/boundary/admin_pages.py`, `app/control/user_admin_controllers.py`, `app/entity/user_accounts.py` and `app/entity/user_profiles.py`. The Manager workflow is in `app/boundary/platform_pages.py`, `app/control/platform_controllers.py`, `app/entity/project_categories.py` and `app/entity/platform_reports.py`. The dates are calculated in `app/common/clock.py`.

## Reporting rules

The report shows **New accounts**, **New projects**, **Project views** and **New saves**. It reads the four counts in one SQLite statement so they come from the same snapshot. The start is inclusive and the end is exclusive. A valid period with no activity displays four zeroes. Dates use the application's existing local timestamps.

New accounts include all roles. A save counts by its `saved_at` even when US22 removes it from the current shortlist. Confirmed project deletion in US30 removes the associated view and favourite events, so regenerating a historical report reflects the deletion. Legacy projects with a removal timestamp are excluded from the three project activity measures.

## Design traceability

The current staff pages use the shared access guard in `app/boundary/ui.py`. In the sequence diagrams, show the guard before the staff Boundary calls its Controller. The account and role tables retain the existing internal `username` and `role_code` columns. The US42 and US47 forms collect the fields in the Final use cases.

For US52, the category Entity combines the name and visible project count in the list query. US57–US59 use a shared `PlatformReports` Entity to read one snapshot. The wireframes use a report selector and four rows. The live report uses three tabs and four metric cards. The Designer and Customer navigation differences are recorded above and in the v3 feedback notes.

## Verification

| Check | Result |
|---|---|
| Received v3 regression suite | 337 passed |
| 34 new checks before application edits | 27 failed and 7 passed |
| Same 34 checks after application edits | 34 passed |
| Final suite | 370 passed across 160 Customer/account checks, 141 Designer/filter checks and 69 Admin/Manager and integration checks |
| Python application statement coverage | 92.58%, 2,808 of 3,033 statements |
| Chrome 156 | 9 workflows passed, including the four roles, uploads, project and category deletion, reports and 390px layout |
| Suspension failure and concurrent writes | Rollback preserved status and sessions. Concurrent duplicate emails, duplicate role names and category removal kept valid data. |
| Local request time | Three requests per story on the supplied demo data. Maximum account/category request 536.4 ms and maximum report request 15.7 ms. |

The new checks are in `tests/test_us42_us59_final.py`. Two inherited test files were updated for intentional Final requirements, including immutable roles, contact validation, one-character categories and the four report metrics. One obsolete invalid-category parameter was removed. The audit, red/green results, final batches, browser run and timing samples are in `us42-us59-evidence/`. The timing samples are sequential Flask test-client requests on this machine.

The original demo database in the release contains 282 accounts, 100 profiles, 110 companies, 120 categories, 320 projects, 1,093 views and 576 favourites. The verification scenarios used separate copies of the database.

## Implementation paragraph for the report

We extended the v3 handover by implementing the remaining User Admin and Platform Manager requirements. The admin workflows validate staff roles, preserve account and profile identity during edits, and revoke sessions atomically when accounts or profiles are suspended. Category management reuses the customer visibility rule for its project counts and protects categories that are in use. The daily, weekly and monthly reports use the same calendar boundaries as the designer statistics and read four activity totals from one SQLite snapshot. We verified the resulting behaviour through automated tests and browser flows spanning all four roles.
