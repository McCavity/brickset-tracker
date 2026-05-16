# SOP-005 — Photo Upload

**Layer:** Tool (execution)
**Goal:** Accept user-uploaded photos during the add/edit flow, stage them safely before a set_id exists, and finalise storage on save. Never overwrite existing photos.

---

## Storage Layout
```
uploads/
  staging/
    {uuid}/          ← temporary, created at upload time
      {timestamp}_{original_filename}
  {set_id}/          ← permanent, created on successful save
      {timestamp}_{original_filename}
```

All paths stored in the DB (`own_photos` field) are **relative to the project root** — never absolute. This ensures the app is portable.

---

## Operation A — Upload Photo (during add/edit)

### Input
```
file:       binary  — uploaded image file
session_id: string  — UUID assigned to this add/edit session (generated on form open)
```

### Steps
```
1. Validate file:
   - Extension must be: .jpg, .jpeg, .png, .webp, .heic
   - Max size: 20 MB
   - Reject anything else with a clear error message

2. Construct staging path:
   staging_dir = uploads/staging/{session_id}/
   filename    = {unix_timestamp_ms}_{original_filename}
   full_path   = {staging_dir}/{filename}

3. Create staging_dir if it does not exist.

4. Write file to full_path.
   - Never overwrite: if filename collision (same timestamp + name), append _1, _2, etc.

5. Return relative path to caller for inclusion in the form's photo list.
```

---

## Operation B — Finalise on Save

### Input
```
session_id: string   — UUID of the staging session
set_id:     integer  — assigned by DB after record insert
```

### Steps
```
1. Source:      uploads/staging/{session_id}/
2. Destination: uploads/{set_id}/
3. Create destination dir if it does not exist.
4. Move all files from source to destination.
   - If a file with the same name already exists in destination (edit flow):
       → append _1, _2, etc. — never overwrite.
5. Delete the now-empty staging/{session_id}/ directory.
6. Return list of final relative paths for DB update.
```

---

## Operation C — Startup Cleanup

### Steps
```
1. List all directories in uploads/staging/.
2. For each directory older than 1 hour (check mtime):
   └─ Delete the directory and all its contents.
3. Log cleanup actions to .tmp/photo_cleanup.log.
```

---

## Edge Cases

| Situation | Behaviour |
|---|---|
| User cancels add flow after uploading photos | Staging dir stays; cleaned on next startup (Operation C) |
| Edit flow: user uploads new photo to existing set | session_id → staging; on save, move to uploads/{set_id}/ alongside existing photos |
| Edit flow: user deletes a photo | Mark as deleted in DB (remove from own_photos JSON); actual file is NOT deleted (append-only storage; manual cleanup only) |
| Upload of HEIC (iPhone photo) | Accept and store as-is; no conversion in MVP |
| Disk full | Return error to user; do not partially save |
| set_id directory already has files | Append-only — existing files are never touched |
