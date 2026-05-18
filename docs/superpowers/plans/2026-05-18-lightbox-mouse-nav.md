# Lightbox Mouse Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the lightbox main-image regression (chevron nav buttons hidden when opened from the hero image) AND add on-image click zones with a JS-driven cursor swap.

**Architecture:** Rewrite `openLightbox` in `templates/details.html` to gather all `.details-photo-thumbs img` on the page as one navigable list (since the main image is always a duplicate of the first thumb). Layer on a click-zone handler that branches on `event.offsetX < halfway`, plus a mousemove handler for the cursor swap. CSS adds one fallback rule for the initial pointer state.

**Tech Stack:** Vanilla JS, plain CSS. No build step, no new dependencies. No Python source changes.

---

## File Structure

| File | Responsibility |
|---|---|
| `templates/details.html` | Lightbox JS lives in the existing IIFE at lines 207–264. Two rewrites + two new event handlers + cleanup. |
| `static/style.css` | One new rule (`.lightbox img.multi`) appended after the existing `.lightbox img` block (around line 1062). |

No new tests — manual smoke covers it (the change is browser-only behaviour).

## Task Order

1. **Task 1**: Fix the regression. Rewrite `openLightbox`'s group discovery + add `.multi` class toggling + cleanup in `closeLightbox`. After this commit, chevron nav buttons appear when opening from the main image and cross-group navigation works.
2. **Task 2**: Add the on-image click zones (left/right halves) + mousemove cursor swap + CSS fallback rule. After this commit, clicking the image halves navigates; cursor swaps on hover.
3. **Task 3**: Final verification + mark Iteration 4.3 done in `task_plan.md`.

---

## Task 1: Fix main-image regression

**Files:**
- Modify: `templates/details.html` lines 225–243 (the `openLightbox` and `closeLightbox` functions inside the lightbox IIFE).

- [ ] **Step 1: Replace `openLightbox`**

In `templates/details.html`, find the existing `window.openLightbox = function (imgEl) { ... };` block at lines 225–236. Replace it with:

```javascript
  window.openLightbox = function (imgEl) {
    if (!imgEl) return;
    // Gather all photos from all thumbs groups on the page.
    // The main image is always a duplicate of the first own (or web) thumb,
    // so we don't include it separately to avoid double-counting.
    const allThumbImgs = Array.from(document.querySelectorAll('.details-photo-thumbs img'));
    if (allThumbImgs.length > 0) {
      activeImages = allThumbImgs;
      // Match by src: if the user clicked the main image, find the thumb
      // with the same src to start at the right index.
      const matchIndex = activeImages.findIndex(img => img.src === imgEl.src);
      activeIndex = matchIndex >= 0 ? matchIndex : 0;
    } else {
      // Edge case: no thumbs rendered (e.g., main is a placeholder). Single-image mode.
      activeImages = [imgEl];
      activeIndex = 0;
    }
    overlayImg.src = imgEl.src;
    overlayImg.classList.toggle('multi', activeImages.length > 1);
    updateNavVisibility();
    overlay.classList.remove('hidden');
  };
```

- [ ] **Step 2: Update `closeLightbox` to clean up the new class + inline cursor**

In the same file, find the existing `closeLightbox` block at lines 238–243:

```javascript
  function closeLightbox() {
    overlay.classList.add('hidden');
    overlayImg.src = '';
    activeImages = [];
    activeIndex = -1;
  }
```

Replace it with:

```javascript
  function closeLightbox() {
    overlay.classList.add('hidden');
    overlayImg.classList.remove('multi');
    overlayImg.style.cursor = '';
    overlayImg.src = '';
    activeImages = [];
    activeIndex = -1;
  }
```

(The `overlayImg.style.cursor = ''` line is preparation for Task 2's mousemove handler. Including it now keeps the cleanup symmetric and avoids a second touch to this function later.)

- [ ] **Step 3: Manual smoke — regression fix**

Start (or confirm) the dev server is running:

```bash
./scripts/launchagent.sh status
```

Expected: server responding (HTTP 200). If not, run `./scripts/launchagent.sh install`.

Open `http://localhost:8000/` in a browser. Find a set with at least 2 photos (own_photos or web_images). Click into `/sets/{id}/`. Click the main hero image to open the lightbox.

**Expected after the fix:**
- Lightbox opens.
- Chevron `<` and `>` buttons appear on the sides (these were hidden before).
- Clicking the chevrons cycles through the photos.
- For a mixed set (own + web), the lightbox walks through ALL photos, not just one group.
- Keyboard `ArrowLeft` / `ArrowRight` still work.

If the buttons still don't appear, hard-refresh the browser (Cmd+Shift+R) to bust any cached `details.html`.

- [ ] **Step 4: Manual smoke — single-photo set**

Find a set with exactly one photo (or temporarily edit one). Open lightbox.

Expected: **NO** chevron buttons appear (single-image mode unchanged).

- [ ] **Step 5: Run pytest to confirm no regression elsewhere**

```bash
.venv/bin/python -m pytest -q
```

Expected: `153 passed`.

- [ ] **Step 6: Commit**

```bash
git add templates/details.html
git commit -m "fix(details): lightbox shows nav buttons when opened from main image (4.3)"
```

---

## Task 2: On-image click zones + cursor swap

**Files:**
- Modify: `templates/details.html` line 253 (replace existing one-line click handler) + add 2 new listeners + new `mousemove` after it.
- Modify: `static/style.css` (append one rule after line 1062).

- [ ] **Step 1: Replace the image click handler**

In `templates/details.html`, find this line (currently line 253):

```javascript
  overlayImg.addEventListener('click', (e) => e.stopPropagation());
```

Replace it with:

```javascript
  // On-image click zones: left half → prev, right half → next.
  // stopPropagation prevents the backdrop's close handler from firing.
  overlayImg.addEventListener('click', (e) => {
    e.stopPropagation();
    if (activeImages.length < 2) return;
    const halfway = overlayImg.getBoundingClientRect().width / 2;
    if (e.offsetX < halfway) step(-1);
    else step(+1);
  });
```

- [ ] **Step 2: Add the mousemove cursor-swap handler**

Immediately after the new click handler (so the two image-related listeners sit together), insert:

```javascript
  // Cursor swap: w-resize over the left half, e-resize over the right half.
  // CSS can't split cursors across one element, so this is JS-driven.
  overlayImg.addEventListener('mousemove', (e) => {
    if (activeImages.length < 2) {
      overlayImg.style.cursor = '';
      return;
    }
    const halfway = overlayImg.getBoundingClientRect().width / 2;
    overlayImg.style.cursor = e.offsetX < halfway ? 'w-resize' : 'e-resize';
  });
```

- [ ] **Step 3: Add the CSS fallback rule**

In `static/style.css`, find the existing `.lightbox img { ... }` block at lines 1056–1062. After its closing brace (line 1062), insert a blank line, then this rule:

```css
/* Multi-image lightbox: cursor swap is JS-driven via mousemove.
   This class only gives a pointer fallback before the first mousemove fires. */
.lightbox img.multi {
  cursor: pointer;
}
```

- [ ] **Step 4: Manual smoke — click zones + cursor swap**

Hard-refresh the browser (Cmd+Shift+R) to load the new JS and CSS. Open a set with at least 2 photos, click into `/sets/{id}/`, open the lightbox.

Run the following checks:

| # | Action | Expected |
|---|---|---|
| a | Hover over LEFT half of image | Cursor becomes `w-resize` (←) |
| b | Hover over RIGHT half of image | Cursor becomes `e-resize` (→) |
| c | Click LEFT half | Previous photo (wraparound at index 0) |
| d | Click RIGHT half | Next photo (wraparound at end) |
| e | Click backdrop (outside image) | Lightbox closes (regression-check) |
| f | Press `ArrowLeft` / `ArrowRight` | Still works |
| g | Press `Escape` | Lightbox closes |

- [ ] **Step 5: Manual smoke — single-photo set**

With a single-photo set, open the lightbox.

| # | Action | Expected |
|---|---|---|
| a | Hover over image | Cursor stays `default` (no `w-resize` / `e-resize`) |
| b | Click image | NOTHING happens (no navigation; click is swallowed by stopPropagation) |
| c | Click backdrop | Lightbox closes |

- [ ] **Step 6: Manual smoke — mixed set close + reopen**

Open the lightbox on a multi-photo set, navigate a few photos, close it (click backdrop or `Escape`). Now open a different set that has only ONE photo, open the lightbox.

Expected: no chevron buttons, cursor is `default`, no inline cursor styling lingering. (This verifies the `closeLightbox` cleanup from Task 1 is correctly removing the `multi` class and inline cursor.)

- [ ] **Step 7: Run pytest to confirm no regression**

```bash
.venv/bin/python -m pytest -q
```

Expected: `153 passed`.

- [ ] **Step 8: Commit**

```bash
git add templates/details.html static/style.css
git commit -m "feat(details): on-image click zones for lightbox navigation (4.3)"
```

---

## Task 3: Mark iteration done

**Files:**
- Modify: `~/.claude/projects/-Users-hhalfpap-git-projects-own-brickset-tracker/memory/task_plan.md` (outside the repo; no commit).

- [ ] **Step 1: Update the Road-to-V1 entry for Iteration 4.3**

Find the line in the task plan:

```
5. **Iteration 4.3** (new, surfaced 2026-05-17 during E2E verification) — lightbox mouse navigation: on-image left/right click zones OR visible nav buttons (with `event.stopPropagation()` to preserve "click backdrop to close"). Small (~15 lines JS + cursor CSS). Could also fold the make_set factory's missing `list_price` parameter into this iteration as a tiny cleanup.
```

Replace with:

```
5. ~~**Iteration 4.3** — lightbox mouse navigation~~ **✅ COMPLETE 2026-05-18** — fixed main-image regression (buttons now visible from any entry point) + on-image left/right click zones with w-resize / e-resize cursor swap. Pure template/CSS change.
```

- [ ] **Step 2: Final verification**

```bash
cd /Users/hhalfpap/git/projects/own/brickset-tracker
git log --oneline 5429f6c..HEAD
```

Expected: two commits with the prefixes from Tasks 1 and 2.

```bash
.venv/bin/python -m pytest -q
```

Expected: `153 passed`.

```bash
./scripts/launchagent.sh status
```

Expected: HTTP 200, server responding.

- [ ] **Step 3: No git commit**

`task_plan.md` lives outside the repo; no commit needed.

---

## Final Verification

- [ ] **Step 1: Two commits since the spec**

```bash
cd /Users/hhalfpap/git/projects/own/brickset-tracker
git log --oneline 5429f6c..HEAD
```

Expected:
- `<sha> feat(details): on-image click zones for lightbox navigation (4.3)`
- `<sha> fix(details): lightbox shows nav buttons when opened from main image (4.3)`

- [ ] **Step 2: All 8 smoke scenarios pass on the live LaunchAgent**

(Spec table — re-run each by hand if not already done as part of Tasks 1–2.)

- [ ] **Step 3: pytest still green**

```bash
.venv/bin/python -m pytest -q
```

Expected: `153 passed`.

Done.
