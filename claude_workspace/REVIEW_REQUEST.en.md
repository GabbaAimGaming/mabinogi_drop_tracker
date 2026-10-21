# Code Review Request: KarenDrop refactoring on `claude/dev-workspace`

> **Status (2026-10-22): closed.** The branch was merged into main via PR #10 and released as v1.1.8. The PR description refers to `a21135c` as the reviewed version. Individual answers to the questions below were not received. Question 5 was resolved in practice by `drop_tool/learning.py` in v1.1.8. Removal pass 2 now follows [AI_RULES.md](AI_RULES.md) rule 4: at the next release prep, the candidates are listed and only those the owner judges fine are deleted. This document is kept as a record.

| | |
|---|---|
| Date | 2026-10-21 |
| Requested by | Repository owner (GabbaAimGaming) |
| Prepared by | Claude (the assistant that made the changes) |
| Repository | https://github.com/GabbaAimGaming/mabinogi_drop_tracker |
| Branch to review | `claude/dev-workspace` (everything on it) |
| Baseline | `main` at `5ed115c` (tag `v1.1.7`) |
| Diff to read | `git diff 5ed115c origin/claude/dev-workspace` |
| Background reading | [HANDOFF.en.md](HANDOFF.en.md) (history, decisions, verification). The Japanese originals are [HANDOFF.md](HANDOFF.md) and [CLAUDE.md](CLAUDE.md) |
| Status of the work | Merged as v1.1.8 (see status note above) |

> Language note: UI strings, log messages and code comments in the repository are in Japanese. Comments marking removal candidates read `[削減候補 2026-10-21]` ("removal candidate, 2026-10-21").

## 1. What we are asking for
Please **read everything on `claude/dev-workspace`** (application code, tests, tools, and the notes and scripts under `claude_workspace/`) and tell us whether the work is **appropriate for the original request** below. Where you are unsure or disagree, we would like to discuss it with you before anything else is done. In particular, please decide whether we may go ahead with "removal, pass 2" (actually deleting the code that is currently commented out).

## 2. The original request (what "appropriate" is measured against)
KarenDrop is a Windows desktop tool (Python 3.12, tkinter, OpenCV, ONNX Runtime) that reads item drops from Mabinogi screenshots and records drop statistics. The owner asked for:

1. **Refactoring without any change in behaviour.** Existing user data (`data/records.json`, `version: 1`) must keep working; nothing that users see or store may change.
2. **End goals**: a lighter codebase with the waste removed, and over-grown code split by responsibility.
3. **Owner's working rules** (added during the work):
   - Work directly on `claude/dev-workspace`; no extra branches.
   - Unneeded code is first commented out with a reason; it is deleted only after the owner confirms (two passes).
   - Share the approach before coding; prioritise correctness, extensibility and ease of change; discuss any behaviour change in advance.
   - Tests: basic tests for anything new; regression tests only for related past features; the full suite only on request.
4. **Release safety**: nothing under `claude_workspace/` or `tests/` may reach a release (see `RELEASE_RULES.md`, `tools/package_release.py`, `tests/test_release_exclusion.py`).

## 3. What is on the branch
Full table with commits in [HANDOFF.en.md §2](HANDOFF.en.md). In short:

| Step | Commit | Change |
|---|---|---|
| 0 | `673d2ed` | Headless stand-ins (`tests/_headless.py`) so logic tests run on Linux |
| 1 | `e7a42e8`, `cc40969` | Read/capture worker moved out of `App.submit` into `read_worker.py`; `poll` → `handle_job` + dispatch table; the `'captured'` event put on watch |
| 2 | `15eab7e` | `red_labels` + `purple_labels` merged into `color_labels.py`; overlap check in `vision.boxes` consolidated |
| 3 | `0f21f81` | `ChestDetector.detect` rewritten as an ordered list of stages |
| 4 | `5b41d7a` | `names.py` and `reading.py` split out of `tracker.py` (re-exported for compatibility) |
| 5 | `dff05b1` | `updater.py` reordered and de-duplicated, deliberately not split |
| Merge | `45f9be6` | Steps 0–5 merged into dev-workspace |
| Housekeeping | `415d48f` | Working rules recorded; obsolete v1.1 source copy removed from `claude_workspace/` |
| 6 | `1a7b565` | **Removal, pass 1**: unused code commented out; three copies of a countdown merged into `App.countdown` |
| 7 | `a24cb34` | **Split**: `app.py` (936 → 471 lines) into `App` + mix-ins `HistoryActions`, `ManualActions`, `SampleActions`; `ui.build_widgets` split into per-area functions |
| Docs | latest commit | This request, English handoff, updated notes and two verification scripts |

## 4. Questions for the reviewer
Please answer each with **Agree / Agree with changes / Disagree / Needs discussion**, plus a short reason.

**A. Overall direction**
1. Is the sequence "restructure → comment out → split → review → delete" a sensible way to reach the stated goals?
2. "Lighter" has not shown up in line counts yet. `drop_tool/` went from 5,453 lines (`main`) to 5,773 now. About 132 of those are commented-out code waiting for pass 2, so after deletion it would be roughly 5,640, still about 190 above `main`. The increase comes from reformatting packed one-liners, added docstrings, and module headers for the new files. Is that acceptable at this stage, or should the remaining work aim for an actual reduction (and if so, where would you look first)?

**B. Behaviour preservation**
3. Each step was checked by feeding the same inputs to old and new code (method syntax trees, recorded call sequences, queue output, results on synthetic images; see [HANDOFF.en.md §2 and §8](HANDOFF.en.md)). Are these checks convincing for each step? Is anything not covered that you would want covered?
4. Step 3 (chest detection) was verified only by stubbing each stage, not with images, because the synthetic images contain no chest (116/116 come back "not found"). Is that reasoning sound?
5. Step 6 comments out `Vision.learn`. It has not been called by the app since v0.18.2, when `item_registration.assign` replaced it. One behaviour existed only in `learn`: removing near-duplicate templates from `records.json`. `assign` does not do this. Matching is unaffected, because `Vision.reload` applies the same 0.98 threshold when loading; the only effect is that `templates` can grow slowly. Is it acceptable to drop it, or should that thinning move into `assign`? (Moving it would be a behaviour change, so we would discuss it first.)
6. The tests that relied on `learn` were rewritten to go through `assign` and `settings.load/save`, with the old versions kept as comments. Do the rewritten tests still protect what the originals protected?

**C. Design of the split (step 7)**
7. `App` is split with **mix-in classes**. They have no `__init__` and rely implicitly on attributes set by `App.__init__` and `ui.build_widgets` (e.g. `self.store`, `self.runs`, `self.rows`). We chose this so that `ui.py` (`command=self.xxx`) and the tests (`App.__new__(App)` with hand-set attributes) work unchanged. Is this the right trade-off, or would you prefer composition (separate controller objects owned by `App`) despite the larger change?
8. Is the grouping right? (History/statistics, manual capture and per-run edits, submission samples; monitoring and dispatch stay in `app.py`.) Are there methods you would place differently? For example, `notify_unregistered` sits in history; `read_failed` stays in `app.py`.
9. We expected to have to change the tests' patch targets (`drop_tool.app.messagebox.*`), but did not need to. Those patches replace attributes on the shared `tkinter.messagebox` module, so they apply wherever the moved methods now live. Do you agree this is reliable, or would you rather point the patches at the new modules explicitly?
10. `updater.py` was deliberately **not** split, because about 20 test patches target names in its own namespace (see HANDOFF §5). Do you agree?

**D. Removal candidates (pass 2)**
11. Is it safe to delete everything marked `[削減候補 2026-10-21]`? List in [HANDOFF.en.md §3](HANDOFF.en.md): `App.test_image`, `App.timed_read`, `retention.EVIDENCE_KEYS/load_settings/save_settings`, `GradientClassifier.compute`, `vision.similarity`, `Vision.learn`, the old countdown bodies, now-unused imports and `STATUS/KIND` in `app.py`, plus the matching old test code.
12. Two items were left out on purpose. What do you recommend?
    - `vision.label_presence`: used only by the private test `test_window_share`.
    - The `'captured'` event: waiting for real-hardware confirmation.
13. Did we miss other dead code, duplication, or files that are still too large? Candidates we noticed but did not touch: `vision.boxes` (86 lines; tuned recognition thresholds that can only be regression-tested with private images), `alt_display.quick_check` (52 lines), `bright_plates.boundaries` (63 lines).

**E. Release and safety**
14. Is anything in the release affected? The new modules live in `drop_tool/` and are imported normally, so the PyInstaller build should pick them up. Please confirm by building the EXE (`python tools/build_exe.py dist`), or tell us it is not needed. Also confirm that the `claude_workspace` contamination guard is intact.

## 5. Known gaps (please weigh these in your verdict)
- **Not run on Windows yet.** All checks were on Linux (Python 3.13, no tkinter). Tests that need a real Tk window, sound or the Windows mutex are skipped there (`test_karen_ui`, parts of `test_item_links` and `test_evidence_retention`, `test_instance_guard`).
- **Private image tests not run.** These need images that are not in the repository: `test_red_labels`, `test_purple_labels`, `test_cyan_labels`, `test_label_*`, `test_reward_samples`, `test_4k_review`, `test_next_4k_samples`, `test_new_person_samples`, `test_closed_oct19`, `test_chest_*`, `test_alt_display`, `test_window_share`, `test_tracker`. The two `test_tracker` tests rewritten in step 6 were run on their own with the module skip removed, and passed.
- **Full suite not re-run after steps 6 and 7.** Following the owner's test rule, only related tests were run (89 and 96 passing). The last full run was 251 passing / 55 skipped, after step 5 and the housekeeping commit.
- `tests/test_tracker.py` is the core test for `Store`, but it is skipped in the public environment, so protection of saving/confirming logic is thin there. No step changed `Store`.

## 6. How to reproduce the checks
```
git clone -b claude/dev-workspace https://github.com/GabbaAimGaming/mabinogi_drop_tracker
cd mabinogi_drop_tracker
python tools/run_tests.py                      # full suite (uses the headless stand-ins where needed)

# Step 7 comparisons (old = the commit before the split)
git worktree add ../old 1a7b565
python claude_workspace/verification/compare_split.py ../old .
python claude_workspace/verification/compare_ui.py ../old .

# Worker comparison (old = step 0, the first commit that has tests/_headless.py; main lacks it)
git worktree add ../step0 673d2ed
python claude_workspace/verification/compare_worker.py ../step0 > old.json
python claude_workspace/verification/compare_worker.py .        > new.json
```
Expected for step 7: `methods differing: []`, `global name mismatches: []`, `same calls: True`, `same app attributes: True`. For the worker comparison, `old.json` and `new.json` should be byte-identical (they were when this request was written). Usage of `compare_vision.py` and `compare_chest.py` is in [HANDOFF.en.md §8](HANDOFF.en.md). On Windows, also launch the app (`start.bat` or `python app.py`) and go through the history tab (register, confirm, delete), manual capture ("3秒後に撮影"), the image check ("画像で確認・読取"), and the submission capture ("提出用撮影（3秒後）").

## 7. How to reply
- One verdict per question in §4 (Agree / Agree with changes / Disagree / Needs discussion), with a short reason.
- An overall verdict on the branch:
  - **Appropriate**: proceed to removal pass 2.
  - **Appropriate with changes**: list the changes.
  - **Not appropriate**: what should be reconsidered.
- Anything you want to discuss live, and any extra checks you want run before pass 2.

Comments on GitHub (on commits or a draft PR) or a written reply are both fine. Nothing further will be changed on the branch until we hear back.
