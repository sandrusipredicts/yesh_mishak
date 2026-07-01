# ISSUE-208 iOS Bundle Identifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify and enforce the ISSUE-183 iOS Bundle Identifier throughout Capacitor, Xcode, documentation, and macOS CI.

**Architecture:** Treat `frontend/capacitor.config.ts` as the shared source of truth and keep Xcode Debug/Release settings aligned with it. Add CI assertions for the committed values and Xcode-resolved build setting before the existing unsigned build.

**Tech Stack:** Capacitor 8, TypeScript, Xcode project settings, GitHub Actions, Bash

---

### Task 1: Verify the approved decision and current configuration

**Files:**
- Inspect: `docs/product-decisions.md`
- Inspect: `frontend/capacitor.config.ts`
- Inspect: `frontend/ios/App/App.xcodeproj/project.pbxproj`
- Inspect: `frontend/ios/App/App/Info.plist`

- [x] Confirm ISSUE-183 approves `com.yeshmishak.app`.
- [x] Confirm Capacitor `appId` is `com.yeshmishak.app`.
- [x] Confirm Debug and Release `PRODUCT_BUNDLE_IDENTIFIER` values are `com.yeshmishak.app`.
- [x] Confirm `Info.plist` resolves `CFBundleIdentifier` from the Xcode setting.

### Task 2: Enforce the identifier in macOS CI

**Files:**
- Modify: `.github/workflows/ios-xcode-validation.yml`

- [x] Assert the committed Capacitor and Xcode values before sync.
- [x] Resolve Xcode build settings and assert `PRODUCT_BUNDLE_IDENTIFIER` before the unsigned build.
- [ ] Open the pull request and confirm the macOS job passes.

### Task 3: Validate and document

**Files:**
- Modify: `docs/product-decisions.md`
- Modify: `.gitignore`

- [x] Replace the stale pre-ISSUE-206 configuration note with the generated iOS project state.
- [x] Document generated config behavior and unsigned CI validation.
- [x] Ignore local tool/runtime artifacts without deleting them.
- [x] Run `npm run build`, `npx cap config`, `npx cap sync ios`, and `npx eslint .`.
- [ ] Commit, push, open a draft pull request, and record the CI result.
