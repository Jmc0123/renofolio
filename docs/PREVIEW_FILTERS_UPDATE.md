Historical snapshot from 3 November 2026. US23-US41 were updated on 6 November; see US23-US41_HANDOVER.md for current behaviour.

# Preview images and combined filters

Updated 3 November 2026

The customer project list now combines keyword, category, Current/Past status and budget. The fictional sample projects have six local AI-generated preview photos matched by room type. This update retains existing accounts and project/activity records.



## How filtering works

- Enter any combination of keyword, category, status and budget, then choose Apply filters.
- A project must satisfy every provided condition (AND). Keyword matches title or description, ignoring English letter case.
- Blank criteria do not restrict the result. If using budget, provide both minimum and maximum; bounds are inclusive and non-negative finite numbers.
- Applying or changing criteria starts on page one. Previous/Next preserves all criteria. Clear all removes all criteria.
- Validation errors retain form values. No-match combinations retain the filters and display a clear empty message.
- If a chosen category disappears, its error is shown and only that category is cleared; the other valid criteria are retained.
- Existing search/category/status/budget URLs still work and can receive the other query parameters too.

Example: `keyword=Kitchen&categoryId=7&status=PAST&minBudget=20000&maxBudget=100000`.

## Preview images

The imagegen skill used the built-in image_gen tool to generate six 1536 x 1024 PNG images. They are architectural photographs of fictional Singapore apartment rooms with warm neutral finishes, natural daylight, realistic proportions, and no people, logos or watermarks.

| Room type | Local file |
|---|---|
| Kitchen | app/static/sample-projects/kitchen.png |
| Living Room | app/static/sample-projects/living-room.png |
| Bedroom | app/static/sample-projects/bedroom.png |
| Bathroom | app/static/sample-projects/bathroom.png |
| Home Office | app/static/sample-projects/home-office.png |
| Dining Room | app/static/sample-projects/dining-room.png |

The complete prompt set is saved beside the images in `generation-prompts.json`. Images are illustrative demo assets reused by room type across styles; they do not establish that a real designer completed those projects. No external image service is needed at runtime.

`generate_test_data.py` now assigns the appropriate photo URL when generating each project. `add_sample_photos.py --db sample_demo.db` fills empty URLs in an existing database, first making a SQLite backup. It preserves non-empty/custom URLs, IDs, account details, favourites, view history and timestamps. Unknown room categories are reported and skipped. Repeating the updater makes no changes once the empty values have been filled.

## Design and code alignment

The original individual-use-case Controllers remain available. The customer list routes now use a shared combined query:

`ProjectFiltersPanel -> SearchAndFilterIDPsController.execute(ProjectFiltersRequest) -> InteriorDesignProjects.searchAndFilter()`

The Boundary renders the single GET form; the Controller validates input; the Entity builds parameterized SQL with AND conditions. The existing public-project visibility rules and route access guard are retained. Update the relevant US13-US17 class and sequence diagrams to show this shared combined query and the form's complete criteria. The product behaviour change is explicitly authorized by the user's 3 November request.

## Starting the updated Desktop project

Stop the currently running server with Ctrl+C, then, from the project folder:

```powershell
$env:IDP_DB_PATH = (Join-Path (Get-Location) 'sample_demo.db')
.\.venv\Scripts\python.exe run.py
```

Open http://127.0.0.1:5000 and refresh. There is no need to rebuild the database or reinstall dependencies for this update.

The shareable ZIP has a clean generated `sample_demo.db`; it does not contain the user's personal Desktop database. The existing Desktop copy is updated by adding photos to its own data.

## Verification

The new regression suite was executed before implementation and failed, then was used to check the completed filters and photo integration. Final automated results, Chrome workflow results and deployment records are stored in `preview-filters-evidence/`.

Actual results on 3 November:

- Before implementation: all 37 new acceptance cases failed against the original Desktop code.
- Final automated suite: 263 passed in 209.38 seconds, including all 226 earlier regression cases.
- Real Chrome browser: 11 workflow checks passed, covering all four criteria, retained form values, pagination, Clear all, validation/empty states, image assets, detail/favourite previews and 390-pixel mobile layout.
- Six PNG assets were generated using the built-in image_gen tool, copied into the project and inspected. New demo generation assigns a room-matched preview to every one of 320 projects.

Desktop installation was completed after the checks. Its Python 3.13.2 / Flask 3.1.3 environment passed all 37 new cases in 10.06 seconds. The existing sample database received 320 photo URLs. Hashes of all non-photo fields and other table data were compared before and after the update and matched. The user's separate original database was also preserved. A code backup is in the Desktop project's parent `upgrade-backups` folder; the pre-photo sample database backup is in `database-backups` inside the existing Desktop project.
