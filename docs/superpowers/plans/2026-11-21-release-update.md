# Release Update Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement and verify these tasks.

**Goal:** Check GitHub for the latest stable Windows release on startup and offer an update with release notes and download progress.

**Architecture:** Python retrieves and validates release metadata, streams the ZIP, and stages verified application files. A separate PowerShell process waits for the running application to exit, swaps the managed files, and rolls back if installation fails. The existing webview presents the release and progress without blocking backup operations.

**Tech Stack:** Python standard library, PowerShell, pywebview, HTML/CSS/JavaScript.

**Spec:** The agreed flow is background discovery, download and install after confirmation, visible progress, and automatic restart.

## Tasks

- [x] Test stable version selection, release notes, progress, checksum checks, and ZIP path validation in `tests/test_updater.py`. Implement networking and staging in `src/updater.py`.
- [x] Exercise the installer with local packages and a forced failure. Package `scripts/install-update.ps1` and wire graceful shutdown through `src/app.py`.
- [x] Add the update panel to the existing UI and document updates in the README.
- [x] Run the test suite, build the portable ZIP, and smoke-test the update from one isolated package to another.

The Windows smoke test updated the v1.1.1 Release package to the local v1.1.2 build. It also verified that an invalid executable triggers a restart of the old version and preserves data in the installation directory.
