# Test evidence

This folder holds the test plan and the results of each test run.

## Rules for what goes here

- Synthetic and public data only. The fake clinic site, made-up subscribers, and test addresses are fine.
- No real organisation names, staff names, client criteria, or client emails. Runs on real organisations stay in the git-ignored `private/` folder.
- Screenshots go in `screenshots/`. Check each one before adding it, and crop anything that is not part of the test.

## How to record a result

1. Run the test as described in `test-plan.md`.
2. Fill in the date, result, and screenshot filename for that row.
3. If a test fails, leave the failure in the table, note what changed, and record the re-run on a new line.

## Automated tests

Run these from the project folder:

```bash
pytest -v
```

Take a screenshot of the output and save it as `screenshots/pytest-YYYY-MM-DD.png`.
