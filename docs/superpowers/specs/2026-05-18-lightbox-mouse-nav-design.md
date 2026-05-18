# Lightbox Mouse Navigation — Design

**Status:** Approved 2026-05-18
**Project:** brickset-tracker
**Iteration:** 4.3 (originally surfaced 2026-05-17, deferred until V1 polish)

## Goal

Fix the lightbox so the prev/next nav buttons actually appear when the user opens the lightbox from the main hero image, AND add on-image click zones as a bigger, more discoverable navigation affordance. Both changes serve the same iteration: making the lightbox feel like a real photo viewer.

## Background

The lightbox in `templates/details.html` already has:
- Visible chevron `#lightbox-prev` / `#lightbox-next` buttons on the sides.
- Keyboard nav (`ArrowLeft`, `ArrowRight`, `Escape`).
- Wraparound (modulo arithmetic in `step()`).
- Backdrop click closes; image click is swallowed via `stopPropagation`.

What's broken / missing:
1. **Regression**: when opened from the main hero image, the buttons stay hidden. The group-discovery in `openLightbox` calls `imgEl.closest('.details-photo-main')` and `querySelectorAll('img')` on that wrapper, which returns 1 image, so `updateNavVisibility()` hides the buttons.
2. **Cross-group nav** isn't supported. Opening a thumb in the own group walks only own photos, even when web photos also exist on the page.
3. **No on-image click zones** — clicking the image does nothing. Users have to aim at the small chevron buttons or use the keyboard.

## Scope

- `templates/details.html` (lightbox JS, ~20 lines changed): rewrite `openLightbox`'s group discovery + extend the image click handler to branch on left/right halves + cursor-swap mousemove handler + `multi` class toggling in open/close.
- `static/style.css` (lightbox CSS, ~3 lines added): one `.lightbox img.multi` rule for the base pointer cursor (cursor swap is JS-driven via mousemove because CSS can't apply different cursors to halves of one element).
- No new tests — template/CSS-only behaviour. Manual smoke covers it.
- Out of scope: touch swipe (separate iteration if needed), changes to how thumbs are rendered, any backend changes.

## JS Implementation

### Rewrite `openLightbox`

The main fix. Replace the group-discovery so all `.details-photo-thumbs img` on the page form one navigable list. The main image is always a duplicate of the first own (or web) thumb, so we don't include it separately.

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

### Click handler with halfway-split

Replace the existing one-liner:

```javascript
overlayImg.addEventListener('click', (e) => e.stopPropagation());
```

with:

```javascript
overlayImg.addEventListener('click', (e) => {
  e.stopPropagation();
  if (activeImages.length < 2) return;
  const halfway = overlayImg.getBoundingClientRect().width / 2;
  if (e.offsetX < halfway) step(-1);
  else step(+1);
});
```

`getBoundingClientRect().width` (not `offsetWidth`) is correct because the lightbox uses `max-width: 90vw; max-height: 90vh; object-fit: contain;` — the *rendered* width and the *natural* width can differ.

### Mousemove handler for cursor swap

Add this handler immediately after the new click handler (so the two image-related listeners sit together). CSS can't apply different cursors to halves of one element, so the cursor is JS-driven:

```javascript
overlayImg.addEventListener('mousemove', (e) => {
  if (activeImages.length < 2) {
    overlayImg.style.cursor = '';
    return;
  }
  const halfway = overlayImg.getBoundingClientRect().width / 2;
  overlayImg.style.cursor = e.offsetX < halfway ? 'w-resize' : 'e-resize';
});
```

### Cleanup in `closeLightbox`

Before the existing `overlayImg.src = ''` line, add:

```javascript
overlayImg.classList.remove('multi');
overlayImg.style.cursor = '';
```

So that the next time the lightbox opens (potentially on a single-image set), no stale state lingers.

## CSS Implementation

Append to the existing `.lightbox img` styles in `static/style.css`:

```css
/* Multi-image lightbox: cursor swap is JS-driven via mousemove.
   This class only gives a pointer fallback before the first mousemove fires. */
.lightbox img.multi {
  cursor: pointer;
}
```

The actual `w-resize` / `e-resize` cursors are set inline by the mousemove handler. The `.multi` rule is only the initial state.

## Testing Strategy

Manual smoke only. Server runs as the LaunchAgent at `http://localhost:8000/`.

| # | Scenario | Expected |
|---|---|---|
| 1 | Single-photo set (1 own, 0 web): click main | Lightbox opens, NO chevron buttons, image clicks do nothing, cursor is `default` |
| 2 | Multi-photo own only (3 own): click main | Buttons visible, left half → prev, right half → next, wraparound, cursor swaps `w-resize`↔`e-resize` |
| 3 | Multi-photo web only (3 web): click any thumb | Same as #2 |
| 4 | Mixed (1 own + 2 web): click main | Lightbox starts on own; navigation steps through all 3 photos (own + web combined) |
| 5 | Mixed: click own thumb | Starts on that own photo; navigation walks all 3 |
| 6 | Mixed: click web thumb | Starts on that web photo; navigation walks all 3 |
| 7 | Keyboard nav | `ArrowLeft`, `ArrowRight`, `Escape` work in all scenarios |
| 8 | Regression check | Main-image open now shows nav buttons (was hidden) |

## Risk + Migration

- **No new dependencies, no Python source changes.** HTML template + CSS only.
- **Cache invalidation:** `static/style.css` isn't versioned with a cache-buster in the link tag. If the browser holds onto an old copy, a hard-refresh is needed once. Not a regression.
- **No data migration.** Nothing in `data/brickset.db` touched.
- **Lightbox UX shift:** in a mixed set (own + web), the lightbox now treats them as one navigable list. The on-page visual divider between the two groups stays. Inside the lightbox, the separation goes away — matches the user mental model of "browse all photos for this set." If a future iteration wants the groups separated inside the lightbox too, that's a separable refinement.

## Done When

- `templates/details.html` updated: new `openLightbox`, new click handler with halfway-split, new mousemove handler, `closeLightbox` cleanup, `multi` class toggling.
- `static/style.css` has the new `.lightbox img.multi` rule.
- All 8 smoke scenarios pass on the live LaunchAgent server.
- `pytest -q` still reports 153 passing.
- Iteration 4.3 marked complete in `~/.claude/projects/-Users-hhalfpap-git-projects-own-brickset-tracker/memory/task_plan.md`.
