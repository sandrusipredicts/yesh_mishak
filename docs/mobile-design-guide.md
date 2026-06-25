# ISSUE-136: Mobile Design Guide

## Purpose

This guide defines the required mobile UI/UX standards for all future mobile remediation work in the project. Developers and contributors must follow these design guidelines to ensure the yesh_mishak web application provides a premium, responsive, and accessible experience on mobile viewports.

## Scope

This guide applies to:

* **User-facing mobile screens**: Login, Registration, Map, Field Details, Create Game, Game Details, and Notifications.
* **Admin mobile screens**: Stats dashboard, Field approval, Game management, User moderation, and Field reports triage.
* **UI Components**: Modals, bottom sheets, forms, buttons, lists, and tables.
* **Layouts**: Hebrew right-to-left (RTL) spacing, margins, grids, and flexboxes.

## Mobile Baseline

All mobile design and implementation work must align with the following baseline parameters:

* **Primary Mobile Viewport**: 360px width and above (e.g., standard Android/iOS viewports).
* **Small Viewport Risk Area**: 320px to 360px width (layouts must wrap or scale gracefully without clipping).
* **Touch-First Design**: All interactive components must be designed for finger tapping rather than mouse clicks.
* **Hebrew RTL-First**: Right-to-left language rules are the default, and translations must not break layouts.
* **Cross-Browser Coverage**: Code must be tested against both Android Chrome and iOS Safari.
* **Virtual Keyboard Adaptability**: Forms must adapt when soft keyboards take up 250px-300px of vertical viewport height.

## Minimum Touch Target Standard

All interactive elements must be large enough to be easily tapped on mobile touchscreens without causing accidental adjacent triggers.

* **Minimum Hit Area**: Every button, link, toggle, input, and tab must meet a minimum size of **44px x 44px**.
* **Preferred Size**: Primary actions (e.g., "Create Game" or "Join Game") should use a height of **48px** or more to increase tap comfort.
* **Icon-Only Buttons**: Circular close `x` buttons, notification bells, settings gears, or location finders must have a click wrapper or padding configured to achieve at least a 44px hit diameter.
* **Inline Actions**: Tab buttons inside tables or lists (e.g., "סימון כנקרא", "Ban", "Approve") must expand their vertical hit targets to 44px via padding, even if their visible text height is smaller.
* **Adjacent Destructive Buttons**: Destructive actions (e.g. Ban vs Suspend, Reject vs Approve) must be separated by space to avoid accidental taps.

### Code Examples

* **Good (Pass)**:
  ```css
  /* Ensuring proper minimum touch height and width */
  .panel-close-button {
    min-width: 44px;
    min-height: 44px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .primary-action-button {
    min-height: 48px;
    padding: 12px 16px;
  }
  ```
* **Bad (Fail)**:
  ```css
  /* Hard-coding tiny targets that cause finger miss-taps */
  .panel-close-button {
    width: 20px;
    height: 20px;
  }
  .admin-action-button {
    height: 25px;
    padding: 4px 10px;
  }
  ```

## Button Spacing Standard

Button arrangements must remain responsive and visually clear on narrow screens.

* **Minimum Spacing**: Adjacent buttons must be separated by a minimum of **8px** gap.
* **Primary / Destructive Spacing**: Action groups (e.g., Approve vs Reject) should prefer a spacing of **12px to 16px** to prevent error taps.
* **Flex Wrapping**: Any container holding multiple buttons (e.g., `.admin-actions`, `.modal-buttons`) must be styled with `flex-wrap: wrap;` so buttons stack vertically instead of overflowing screen boundaries.
* **Visual Dominance**: The primary positive action must be styled with high-contrast background colors, while secondary actions use outlines or muted backgrounds.
* **Full-Width Layout**: On screens <= 640px, action buttons inside forms or bottom panels should occupy 100% of the container width to increase usability.
* **Bottom Insets**: Sticky action buttons placed at the bottom edge must respect safe area offsets.

## Form Spacing Standard

Forms must remain readable, aligned, and navigable when focused.

* **Prevent iOS Auto-Zoom**: Text input fields, selects, and textareas must have a minimum `font-size: 16px` on mobile viewports. Browsers will automatically zoom the page if focused input font sizes are under 16px.
* **Input Height**: The minimum vertical height for inputs, selects, and textareas must be **44px**.
* **Label Spacing**: Labels must have **6px to 8px** spacing above their respective inputs.
* **Field Spacing**: Adjacent form field groups must have **12px to 16px** vertical spacing.
* **Section Spacing**: Major form sections must be separated by **20px to 24px**.
* **Inline Validation Errors**: Error messages must render near the field they apply to, rather than as a single global error at the bottom.
* **Global Messages**: If global errors are necessary, they must render near the active submit button and be automatically scrolled into view.
* **Numeric Keypads**: Integer inputs (e.g., participant counts) must include `inputmode="numeric"` and `pattern="[0-9]*"` to display a clean numerical keypad instead of an alphanumeric keyboard.
* **Scroll Safety**: Form wrappers must remain scrollable to allow recovering fields when keyboards overlap.

## Modal and Bottom Sheet Standard

Modals and bottom sheets must be bounded to prevent viewport overflow and user entrapment.

* **Max Height Restriction**: Modals and slide-in panels must be constrained using relative units to prevent them from growing larger than the visible screen (e.g. `max-height: calc(100vh - 40px)` or `max-height: calc(100dvh - 32px)`).
* **Internal Scrolling**: If content height exceeds the modal boundaries, developers must apply `overflow-y: auto;` to the content container.
* **Sticky Navigation**: Close buttons (`x`) and modal header labels must remain sticky/fixed at the top of the container, so they do not scroll out of view.
* **Dynamic Content Bounds**: Avoid layouts that dynamically expand in height (e.g. toggling lists inline) without capping parent sheet height.
* **Reachability**: Actions (Submit/Cancel) must be placed in a fixed bottom container or positioned so the user can easily scroll to reach them.

## Safe Area Rules

To ensure content is readable and interactive elements are clickable on devices with screen notches and gesture home indicators (e.g. modern iPhones), safe area offsets must be applied.

* **Bottom Panels**: Bottom sheets and sticky buttons must incorporate `padding-bottom: env(safe-area-inset-bottom)` or use `calc(...)` to combine it with standard padding.
* **Critical Actions**: Critical actions (such as Close or Save) must never be positioned flush against the viewport bottom edge.
* **Floating Buttons**: Floating Action Buttons (FABs) must set bottom positions to at least `calc(16px + env(safe-area-inset-bottom))` to clear OS gesture zones.

## Keyboard Handling Standard

Virtual keyboards occupy a large portion of the viewport height on mobile devices, which must be handled cleanly.

* **Visible Focus**: Focused input fields must remain visible and not be obscured by the active keyboard.
* **Cancelable Forms**: Close controls or cancel actions must remain reachable or scroll-accessible while typing.
* **Dynamic Viewports**: Avoid using static height rules like `100vh` on form pages; instead, prefer `100dvh` (Dynamic Viewport Height) or let the height grow automatically with scroll enabled.
* **Scroll Container**: Never apply `overflow: hidden` to form screens or modal wrappers.

## Lists and Tables Standard

Admin and user tables must adjust their layouts for small viewports.

* **Hebrew Wrap**: Text must wrap naturally inside list items. Long emails or names must not wrap with clipping or create horizontal scroll.
* **Table Horizontal Scroll**: Data tables (like lists of users, games, or field reports) must be placed inside a wrapper with `overflow-x: auto;` and have visual edge indicators (fade shadows, scrollbars) to signify scrollability.
* **Alternative Card Layout**: Where possible, prefer converting multi-column table rows into stacked card blocks on viewports <= 640px.
* **Row Actions**: Table actions (edit, delete, ban) must remain accessible by scrolling the row horizontally or opening a details sheet.
* **Empty and Loading States**: Missing data or loading indicators must not push actions off-screen.

## Hebrew RTL Standard

RTL layout rules must be consistently applied for Hebrew language sessions.

* **Directionality**: Text and layout elements must match RTL conventions (using `direction: rtl`, `flex-direction: row-reverse`, or logical properties like `margin-inline-start`).
* **Number and Time Formats**: Numbers, dates, and times inside Hebrew text must be localized correctly (avoiding reverse timezone offsets or text layout breaks).
* **Copy Length**: Spacing must accommodate Hebrew words, which are often longer or shorter than their English equivalents.
* **Label Collisions**: Long Hebrew labels must not overlap icons or buttons.

## Notification UI Standard

The notification center must remain dense, responsive, and readable.

* **Auto-Wrap**: Notification titles and bodies must wrap naturally without overflow.
* **Badge Density**: Count badges must align cleanly and have sufficient contrast.
* **Empty Lists**: Empty notification states must show localized feedback (e.g. "אין התראות").
* **Target Sizes**: Tapping a notification card to dismiss it or mark it read must follow the 44px hit standard.

## Admin Mobile Standard

Admin panel screens must be hardened against accidental moderation mistakes on touchscreens.

* **Action Spacing**: Moderation actions (Ban, Reject, Suspend) must use clear colors (red/yellow) and be separated from positive actions (Approve, Unban) to avoid mis-taps.
* **Custom Dialogs**: Important moderation actions must not rely on browser-native `window.prompt` or `window.confirm`. Replace them with custom React modals to ensure proper keyboard handling.
* **Context Preservation**: Moderation rows must display the target user's context (email/username) clearly, even when scrolling horizontally.

## Accessibility and Usability Standard

Remediation work must maintain accessibility guidelines.

* **Labeling**: Every input field must have an associated `<label>` or `aria-label`.
* **State Colors**: Color must not be the only indicator of a state (e.g. warning icons must accompany yellow highlights).
* **Contrast**: Ensure a minimum 4.5:1 text color contrast ratio on all viewports.
* **Disabled States**: Buttons in a loading or disabled state must be visually distinct and not accept tap events.

## Engineering Standards for Mobile Fixes

* **Finding ID Tracking**: Every mobile PR and commit must reference the finding ID it resolves (e.g., `Resolves ML-MAP-001`).
* **Desktop Integrity**: Changes made to support mobile views must not break the desktop layout or functionality.
* **Strict Scoping**: Focus each fix on one component or screen. Do not bundle multiple independent fixes or unrelated refactors into a single branch.
* **Linter & Build**: Code must compile without errors, and ESLint must pass (or only output documented baseline exceptions).
* **Mobile Verification**: Add validation notes to PRs detailing which emulated viewports and physical devices were tested.

## Recommended CSS Tokens / Constants

The following design tokens are recommended for future mobile CSS variables (to be documented only; do not add to runtime stylesheet files in this issue):

```css
:root {
  /* Minimum touch target size */
  --mobile-touch-target-min: 44px;
  
  /* Preferred height for primary buttons */
  --mobile-primary-action-height: 48px;
  
  /* Standard spacing between small controls */
  --mobile-control-gap: 8px;
  
  /* Standard spacing between page sections */
  --mobile-section-gap: 20px;
  
  /* Standard gap between form fields */
  --mobile-field-gap: 12px;
  
  /* Standard modal margins */
  --mobile-modal-margin: 16px;
  
  /* Bottom padding incorporating safe areas */
  --mobile-safe-bottom-padding: calc(16px + env(safe-area-inset-bottom));
}
```

## Acceptance Checklist

All future mobile PRs must be verified against this checklist before approval:

* [ ] All interactive buttons, inputs, tabs, and links have a touch target of at least 44x44px.
* [ ] Inputs, selects, and textareas use a minimum font size of 16px on mobile viewports.
* [ ] Modals, bottom sheets, and slide-in panels constrain their height and use `overflow-y: auto`.
* [ ] Virtual keyboard activation does not clip inputs, hide submit buttons, or trap users.
* [ ] Submit and Cancel buttons remain reachable without forcing user zoom.
* [ ] Long Hebrew text wraps safely without creating horizontal page overflow.
* [ ] Bottom sticky buttons and sheet panels use safe-area-aware padding (`env(safe-area-inset-bottom)`).
* [ ] Destructive actions are visually distinct, colored clearly, and spaced safely from other actions.
* [ ] Local frontend builds compile successfully, and the linter reports zero new errors.
* [ ] The PR documentation references the specific finding IDs resolved.

## Final Verdict

Mobile remediation can now proceed. All future mobile fix pull requests must be validated against the standards defined in this guide.
