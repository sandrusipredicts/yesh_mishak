# ISSUE-209 iOS Code Signing Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish an official, security-conscious iOS code-signing strategy without configuring real signing.

**Architecture:** Keep current simulator and macOS CI validation unsigned. Define organization-owned Apple account roles, local development signing boundaries, protected TestFlight/production workflows, credential custody, renewal, and incident controls as future gated work.

**Tech Stack:** Markdown, Apple Developer Program, App Store Connect, GitHub Actions

---

### Task 1: Audit Current State

**Files:**
- Inspect: `docs/ios-development-environment.md`
- Inspect: `docs/mobile-build-strategy.md`
- Inspect: `.github/workflows/ios-xcode-validation.yml`
- Inspect: `frontend/ios/App/App.xcodeproj/project.pbxproj`

- [x] Confirm the existing CI build explicitly disables signing.
- [x] Confirm no Apple Team ID is committed.
- [x] Confirm no signing certificate, provisioning profile, private key, or Xcode user data is tracked.

### Task 2: Define the Strategy

**Files:**
- Create: `docs/ios-code-signing-strategy.md`

- [x] Define development, TestFlight, and production signing decisions.
- [x] Define organization ownership, named roles, custody, renewal, and incident handling.
- [x] Define unsigned and signed CI separation plus proposed secret names.
- [x] Add the required final decision table and future implementation gates.

### Task 3: Record and Validate the Decision

**Files:**
- Modify: `docs/product-decisions.md`

- [x] Append the ISSUE-209 decision record.
- [x] Run documentation, scope, secret-asset, and native-file validation.
- [x] Commit only documentation changes and confirm a clean working tree.
