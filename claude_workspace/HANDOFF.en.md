# Handoff Notes: Refactoring (updated 2026-10-21)

> English translation of [HANDOFF.md](HANDOFF.md). The Japanese version is the source of truth; if the two disagree, follow the Japanese one.
> UI strings, log messages and code comments in the repository are in Japanese. Where this document quotes them, an English gloss is given in brackets.

Work happens on **`claude/dev-workspace`**. The code map is [CLAUDE.md](CLAUDE.md) (Japanese) and the release-exclusion rules are in [RELEASE_RULES.md](RELEASE_RULES.md) (Japanese). The review request is [REVIEW_REQUEST.en.md](REVIEW_REQUEST.en.md).

**Current status: waiting for review.** New work is paused until the reviewer has gone through dev-workspace and come back with a judgement on whether it is appropriate for the original request.

## 0. Working rules (set by the owner on 2026-10-21; mandatory)
1. **Work on `claude/dev-workspace`.** Do not create separate branches such as `refactor/*`; commit to dev-workspace directly.
2. **Never delete unneeded code in one go. Use two passes.**
   - Pass 1: comment it out, with a one-line comment saying what is unneeded and why (e.g. `# [削減候補 2026-10-21] 呼び出し元なし。確認後に削除` ["removal candidate: no callers; delete after confirmation"]). Comment out or skip the tests that depend on it in the same way.
   - Pass 2: delete it once the owner has checked and said it is fine.
   - Exception: things the owner has explicitly said may be deleted (e.g. the v1.1 source copy that used to live in `claude_workspace/`) may be deleted directly.

## 1. The original request and the overall flow
- **Request**: tidy up the code of KarenDrop (a drop-tracking tool for the game Mabinogi, v1.1.7) **without changing its behaviour**. The end goals are "a lighter codebase with the waste removed" and "splitting over-grown code by responsibility".
- **How it has gone**:
  1. **Restructuring (steps 0–5)**: built a base on which the tests can run, split up large routines, and merged duplicates. The line count actually went up (reformatting and added docstrings).
  2. **Removal, pass 1 (step 6)**: found unused code and commented it out (not deleted yet).
  3. **Split (step 7)**: split the 936-line `app.py` into four files by responsibility.
  4. **Review (we are here)**: the reviewer reads all of dev-workspace.
  5. **Removal, pass 2**: after the review and the owner's confirmation, actually delete the places marked `[削減候補 2026-10-21]`.
- **Promise shared by every step**: behaviour does not change. Each step was checked by feeding the same inputs to the old and new versions and comparing the results (right-hand column in §2).

## 2. Summary by step

| Step | Commit | What changed | How "no behaviour change" was checked |
|---|---|---|---|
| 0 | `673d2ed` | `tests/_headless.py`: installs stand-ins for tkinter, winsound and `WinDLL` only where they are missing, so the logic tests can run on Linux. Link detection consolidated into `updater._is_link` | 159 run with 22 errors → 246 passing |
| 1 | `e7a42e8` | Moved `work()` out of `App.submit` into `drop_tool/read_worker.py` (`run`/`_observe`/`_burst`). `poll` → `handle_job` plus a mode→handler table. `getattr` defaults moved to class attributes. Reformatted the packed one-liners in `app.py` | Queue output identical across 14 scenarios fed to old and new (`verification/compare_worker.py`) |
| 1' | `cc40969` | Commented out handling of the `'captured'` event (on watch). If one arrives it is logged to `errors.log` and ignored | 1 test skipped |
| 2 | `15eab7e` | `red_labels` + `purple_labels` → `color_labels.py` (`red`/`purple`). Overlap check in `vision.boxes` consolidated into `_overlaps` | Candidates, `Vision.boxes`, `quick_check` and scale correction identical on all 316 synthetic images (`compare_vision.py`) |
| 3 | `0f21f81` | `ChestDetector.detect` rewritten as an ordered list of stages (`_near_plates`/`_detail`/`_parts`). Helper detectors are `cached_property` | Chosen result, call order and detector construction count identical across 384 combinations with each stage stubbed (`compare_chest.py`). No image comparison, because it would be meaningless (CLAUDE.md §7) |
| 4 | `5b41d7a` | Split `names.py` (`normalize`) and `reading.py` (`StableReading`/`consensus`) out of `tracker`; `tracker` re-exports them. Two hand-written normalisations in `item_links` replaced with `normalize` | The 8 moved definitions have identical syntax trees. `Store` and `records.json` unchanged |
| 5 | `dff05b1` | Did not split `updater`; reordered its contents into fetch / validate / apply & roll back / for distributors, and turned repeated values into constants | With the new constants substituted back, all 33 definitions match the old syntax trees |
| Merge | `45f9be6` | Merged into dev-workspace. `package_release.py` keeps both the contamination guard and main's slimmer bundle | 251 passing (including `test_release_exclusion`) |
| Housekeeping | `415d48f` | Added the working rules (§0). Deleted the v1.1 source copy in `claude_workspace/` (owner approved) | 251 passing |
| 6 | `1a7b565` | **Removal, pass 1**: commented out unused code. Merged the 3-second countdown into `App.countdown` (§3) | 89 related tests passing. Confirmed the new `report_missed` test also passes on the old code |
| 7 | `a24cb34` | **Split**: moved methods out of `app.py` into `HistoryActions`, `ManualActions` and `SampleActions`. `ui.build_widgets` split into per-area functions (§4) | 63 methods identical by syntax tree, and the names they reference resolve to the same objects (`compare_split.py`). 171 widget calls identical (`compare_ui.py`). `compare_worker.py` identical. 96 related tests passing |

## 3. Removal, pass 1 (step 6) in detail
Search for `[削減候補 2026-10-21]` to find every place.

| Target | Reason | Tests |
|---|---|---|
| `App.test_image` | No callers; it only calls `review_capture` | — |
| `App.timed_read` | Not called from the app (its docstring says "for the old call path") | One test in `test_capture_flow` stopped |
| `retention.EVIDENCE_KEYS`, `load_settings`, `save_settings` | The app uses `settings.load/save` directly. `load_settings` turned out to be unused as well | `test_evidence_retention` rewritten to go through `settings.load/save` |
| `GradientClassifier.compute` | Left over from `cv2.HOGDescriptor` compatibility; `ChestShape` only uses `detectMultiScale` | — |
| `vision.similarity` | Matching uses `mask_similarity` on masks that are already built | — |
| `Vision.learn` (and `import copy` in `vision`) | See "History" below | Two public tests and two in the private `test_tracker` rewritten to use `assign`; one test specific to `learn` stopped |
| Three copies of the countdown | `capture_manual`, `report_missed` and `timed_read` had the same code. Merged into `App.countdown(seconds, text, mode)`; old code kept as comments | Basic test for `report_missed` added |

**History of `Vision.learn`**: it stored a label image as a matching template when a misread was corrected by hand. From the first commit (Oct 13) `correct_row` called it, and it overwrote the row's name directly. In v0.18.2 (Oct 18) it was replaced by `item_registration.assign`, which keeps the original read name and maps misread name → official name through `item_links`. Since then nothing in the app calls it. One behaviour existed only in `learn`: dropping near-identical templates (similarity ≥ 0.98) from the records. `assign` does not do this. However, `Vision.reload` thins templates by the same threshold when loading, so matching is unaffected. The only difference is that `templates` in `records.json` can grow slowly.

**Deliberately left out**: `vision.label_presence` (a one-line wrapper used only by the private `test_window_share`; to be decided with the owner). The `'captured'` event (still being watched on real hardware, §6).

## 4. The split (step 7) in detail
- `app.py` (936 → 471 lines): start-up, settings, foreground capture, the monitoring loop, and dispatch of read results (`handle_job`, `apply_live`, `read_failed`).
- `history_actions.py` (`HistoryActions`): showing history and statistics, row selection and preview, dictionary registration `correct_row`, confirm / exclude / delete, CSV export, notice about unregistered names. The display labels `STATUS` and `KIND` moved here too.
- `manual_actions.py` (`ManualActions`): `countdown`, capture after 3 seconds, checking and reading a captured image, saving a manual read, editing within one run.
- `sample_actions.py` (`SampleActions`): saving submission samples, the "could not read" report, ZIP export.
- `App` inherits all three (`class App(HistoryActions, ManualActions, SampleActions)`). None of the three has an `__init__` or class attributes; they are mix-ins that rely on App's attributes.
- `ui.build_widgets` (143 lines) is split within the same file into `_controls`, `_notes`, `_stats_tab` and `_review_tab`. The order in which widgets are created is unchanged. Since the file was touched, the one packed line in it was reformatted.
- Imports no longer used in `app.py`, and `STATUS/KIND`, are commented out per §0 (the real ones live in the new files).

## 5. Decision log (why things were done this way)
- **The queue stays a plain tuple**: tests push bare `(epoch, mode, result, error)` tuples to test `poll`.
- **Imports are not moved inside functions**: tests patch module attributes.
- **`updater` is not split (option A)**: tests patch `updater.build_opener`, `download`, `check` and others in about 20 places. After a split the moved functions would look up names in their own module, the patches would no longer apply, and real network calls could happen during tests. No new networking features are planned either.
- **`App` is split with mix-in classes**: `ui.py`'s `command=self.xxx` and the tests' `App.__new__(App)` keep working unchanged.
- **The `App` split did not change any test patch targets**: at first a rewrite looked necessary (and the owner had approved it). But `patch('drop_tool.app.messagebox.askyesno')` replaces an attribute on the `tkinter.messagebox` module object itself, so it also takes effect in the new modules. Unlike `updater`, the patch target is not "a name in the module's own namespace".
- **Chest detection is not compared with images**: synthetic images contain no chest, so every stage finds nothing. In practice 116 out of 116 images came back "not found", exercising only the "nothing found" path.
- **Only touched files are reformatted**: reformatting everything would bloat the diff. Reformatted so far: `app.py`, `read_worker.py`, `vision.py`, `color_labels.py`, `chest_detector.py`, `updater.py`. The new `*_actions.py` files keep the original formatting as moved (so the syntax-tree comparison stays exact).
- **Tests depending on `Vision.learn` were rewritten, not removed**: the properties they protected (a template still matches after restart; the user's exclusion beats the bundled material; a failed save rolls everything back) should still be protected on the current code path.

## 6. What is left (by priority)
1. **Review** ([REVIEW_REQUEST.en.md](REVIEW_REQUEST.en.md)): wait for the reply.
2. **Check on Windows (not done yet)**: `python tools/run_tests.py`, then launch the app on real hardware and go through each tab, the buttons, and automatic/manual reading. Screens, sound and the mutex could not be checked on Linux. Step 7 moved App's screen actions across files, so pay particular attention to the history tab (register, confirm, delete), manual capture and the submission capture.
3. **Private image tests (in the owner's environment)**:
   - Step 2: `test_red_labels`, `test_purple_labels`, `test_cyan_labels`, `test_label_*`
   - Step 3: `test_reward_samples`, `test_4k_review`, `test_next_4k_samples`, `test_new_person_samples`, `test_closed_oct19`, `test_chest_*`
   - Steps 1, 4, 6: `test_alt_display`, `test_window_share`, `test_tracker` (step 6 rewrote its two learning tests to use `assign`; here they were run on their own with the skip removed and passed)
4. **Removal, pass 2**: after the review and the owner's confirmation, delete everything marked `[削減候補 2026-10-21]` (app and tests).
5. **Watching `'captured'`**: if `errors.log` never shows "想定外のcapturedイベントを受信しました" ["received an unexpected captured event"] on real hardware, delete it all together: the guard in `App.handle_job`, the commented lines in `App.show_progress`, the one skipped test in `test_alt_display`, and `notification.SOUNDS['captured']`.
6. **What to do with `vision.label_presence`**: decide with the owner.
7. **Delete the six remote `refactor/step*` branches** (the owner, from GitHub's Branches page; the session was refused with HTTP 403).
8. **When bringing this back to main**: the contamination guard (`RELEASE_EXCLUDED_DIRS`) exists only on dev-workspace. Follow the pre-publication checks in `AGENTS.md` when opening the PR.

## 7. Agreements with the owner (how to work)
- The working rules in §0 (work on dev-workspace; comment out → confirm → delete).
- Share the implementation approach once before coding.
- Present source changes as diffs. Full files only when asked.
- Put correctness, extensibility and ease of change first. Discuss any behaviour change beforehand.
- Tests: basic tests for anything new; regression tests only for past features related to the change. Run the full suite only when asked.
  - Steps 0–5 ran `tools/run_tests.py` (about 10 seconds) every time. Steps 6 and 7 ran only the related tests (89 and 96). The full suite has not been run since.
- Run the `AGENTS.md` checks before publishing anything (push, PR, Release).

## 8. Verification scripts (`verification/`)
Prepare the old version with `git worktree add <path> <old commit>`, run the script against old and new, and compare.
- `compare_worker.py`: queue output of `App.submit`/`read_worker` (14 scenarios). Argument: repository. Compare the JSON from old and new
- `compare_vision.py`: coloured labels, `Vision.boxes`, `quick_check`, scale correction (316 synthetic images). Arguments: repository, output JSON
- `compare_chest.py`: stage control of chest detection (384 combinations). The image comparison part is commented out. Arguments: repository, output JSON
- `compare_split.py`: step 7. Arguments: old repository (`1a7b565`), new repository. Prints whether method syntax trees and referenced objects match
- `compare_ui.py`: step 7. Arguments: old repository (`1a7b565`), new repository. Compares `build_widgets`' widget-call sequence and App attributes

Run tests through `python tools/run_tests.py`, which installs the stand-ins from `tests/_headless.py` (plain `python -m unittest` does not).
