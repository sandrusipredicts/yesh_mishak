# Frontend Performance Audit Checklist

Manual checklist for measuring frontend rendering performance.
Created for ISSUE-083. Run these checks in Chrome DevTools.

## Prerequisites

- Chrome browser with DevTools open
- App running locally (`npm run dev`) or on staging
- Performance tab and React DevTools extension installed
- Enough test data to exercise each area (ideally 50+ fields, 10+ notifications)

## 1. Marker Rendering (MapPage)

### Visual frame check
1. Open the map with 50+ fields loaded
2. DevTools > Performance > Record
3. Pan the map rapidly (3-4 fast drags in different directions)
4. Stop recording
5. Check:
   - [ ] Total scripting time per `moveend` cycle (look for `handleFieldsLoaded`)
   - [ ] Any frames > 50ms in the flame chart during pan
   - [ ] DOM node count (Elements panel > Ctrl+Shift+P > "dom statistics")

### JSON.stringify cost
1. Performance tab > Record
2. Trigger a single map pan that reloads fields
3. Stop recording
4. Search flame chart for `JSON.stringify`
5. Check:
   - [ ] Duration of `JSON.stringify` calls inside `handleFieldsLoaded`
   - [ ] Whether the stringify runs on every load even when data hasn't changed

### localStorage write cost
1. Same recording as above
2. Search for `setItem` in the flame chart
3. Check:
   - [ ] Duration of `localStorage.setItem` for cached fields
   - [ ] Size of data written (Application tab > Local Storage > `cached_fields`)

## 2. Notification Inbox Modal

### Open with many notifications
1. Ensure 50+ notifications exist (including mix of read/unread)
2. Performance > Record
3. Click the bell icon to open NotificationInboxModal
4. Stop recording
5. Check:
   - [ ] Time from click to modal visible
   - [ ] Whether all notifications render at once (no virtualization)
   - [ ] Number of DOM nodes added when modal opens

### Mark-all-read re-render
1. With modal open and unread notifications present
2. Performance > Record
3. Click "Mark all read"
4. Stop recording
5. Check:
   - [ ] Whether entire notification list re-renders
   - [ ] Number of state updates (look for multiple `setState` calls)

## 3. Game Panel / Field Details

### Field selection
1. With 50+ fields loaded on map
2. Performance > Record
3. Click a field marker to open FieldDetailsPanel
4. Stop recording
5. Check:
   - [ ] Time from click to panel visible
   - [ ] Whether opening the panel causes any map re-render

### Upcoming games list
1. Select a field with multiple upcoming games
2. Check:
   - [ ] Each upcoming game creates a separate GamePanel with its own timer interval
   - [ ] Number of active `setInterval` timers (Sources tab > Event Listener Breakpoints)

## 4. Admin Pages

### All Fields table
1. Navigate to Admin > Fields > All Fields tab
2. Performance > Record from tab click to table fully rendered
3. Check:
   - [ ] Time to load and render the full fields table
   - [ ] Whether all rows render at once (no pagination in DOM)
   - [ ] DOM node count after table renders

### Users table with search
1. Navigate to Admin > Users
2. Wait for table to load
3. Performance > Record
4. Type in the search field
5. Stop recording
6. Check:
   - [ ] Whether the table re-renders on every keystroke
   - [ ] Cost of `matchesSearch` filter per keystroke (look in flame chart)

### Games table
1. Navigate to Admin > Games
2. Check:
   - [ ] Both active and finished games tables render all rows at once
   - [ ] Extend/Close actions trigger full `loadGames()` reload

## 5. Unread Count Polling

1. DevTools > Network tab
2. Leave the app open for 2+ minutes
3. Check:
   - [ ] Polling interval matches UNREAD_COUNT_POLL_MS (20s prod, 1s dev)
   - [ ] Each poll triggers only the unread count endpoint, not full notification reload
   - [ ] No re-renders of MapPage on each poll when count hasn't changed

## Recording results

For each section, note:
- Measured or inferred?
- Browser (Chrome version)
- Device type (desktop/mobile)
- Data size (field count, notification count, user count)
- Key timings from Performance tab

## ISSUE-084 before/after measurement

ISSUE-084 removed the full `JSON.stringify` field-array comparison, reduced unchanged-field localStorage writes, and debounced map `moveend` field loading. Runtime FPS/frame timing still requires manual browser measurement.

### Before/after steps

1. Run the app against the same backend/test data before and after the ISSUE-084 change.
2. Use the same browser, device, zoom level, viewport size, and field count for both runs.
3. Open DevTools > Performance and record a rapid pan sequence with 3-4 map drags.
4. Stop recording and compare:
   - [ ] FPS / frames during pan.
   - [ ] Long frames over 50ms.
   - [ ] Scripting time during field reload.
   - [ ] Whether `JSON.stringify` appears inside `handleFieldsLoaded`.
   - [ ] Whether `localStorage.setItem` appears when the field fingerprint did not change.
   - [ ] Number of `GET /fields` requests during rapid panning.
5. Record results:
   - Before FPS / long-frame count:
   - After FPS / long-frame count:
   - Field count:
   - Browser/device:
   - Notes:

FPS was not automatically measured by the ISSUE-084 code/build validation. Do not claim FPS improvement until this manual browser recording is complete.
