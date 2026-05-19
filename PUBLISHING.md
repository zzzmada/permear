# How to publish this release (avoids git merge conflicts)

This file is for the **maintainer**. Not part of the public docs.

The previous publishing attempt for v7.2 failed because a git merge was attempted between v5.7 (in main) and v7.2 (incoming). The merge created conflict markers that made YAML invalid. We avoid this by **replacing**, not merging.

---

## Step-by-step publish

### 1. Clone fresh

On your local machine (not on the HA instance):

```bash
mkdir -p ~/projects && cd ~/projects
git clone https://github.com/zzzmada/permear permear-publish
cd permear-publish
```

You should be on `main` branch (currently v7.2.0).

### 2. Hard reset to remote main

```bash
git fetch origin
git reset --hard origin/main
```

### 3. Delete everything except .git

```bash
find . -maxdepth 1 ! -name '.git' ! -name '.' -exec rm -rf {} \;
ls -la
# Should show only .git
```

### 4. Extract the new tarball

```bash
cd ~/projects/permear-publish
tar -xzf ~/Downloads/permear-v7.3.tar.gz --strip-components=1
ls -la
# Should show README.md, CHANGELOG.md, scripts/, etc.
```

### 5. Verify no conflict markers

```bash
grep -rn "^<<<<<<<\|^=======$\|^>>>>>>>" . 2>/dev/null
# Should print nothing
```

### 6. Validate YAML and Python

```bash
python3 -c "
import yaml
class L(yaml.SafeLoader): pass
L.add_constructor('!secret', lambda l, n: 'SEC')
L.add_constructor('!include', lambda l, n: 'INC')
L.add_constructor('!include_dir_named', lambda l, n: 'INC')
yaml.load(open('automations/permear.yaml'), Loader=L)
yaml.load(open('configuration_additions.yaml'), Loader=L)
yaml.load(open('memory/lovelace_card.yaml'), Loader=L)
print('YAML OK')
"

python3 -c "
import ast, os
for root, dirs, files in os.walk('scripts'):
    for f in files:
        if f.endswith('.py'):
            ast.parse(open(os.path.join(root, f)).read())
print('Python OK')
"
```

### 7. Stage and commit

```bash
git add -A
git status
# Should show all changes as "modified" or "added"

git commit -m "v7.3.0: stability and concurrency safety

Stability release focused on hardening v7.2:
- File locking (fcntl.flock) in all memory mutators
- Atomic write via temp + rename in save_json
- locked_update() context manager for atomic read-modify-write
- validate_ha_config() before reload (rollback if invalid)
- Reverse-seek log tail (O(1) RAM)
- Bulk fetch /api/states (1 call vs N sequential)
- AI Task entities centralized in secrets.yaml
- Circuit breaker tracks JSON parse failures

No new user-facing features. Almost transparent upgrade for v7.2 users
(just add 2 new secrets). See MIGRATION.md.

New ROADMAP.md describes the path to v10 HACS release, including the
ARAS Filter (v7.5) inspired by the Ascending Reticular Activating System
and the 3-tier memory model (v7.6)."
```

### 8. Tag the release

```bash
git tag -a v7.3.0 -m "PERMEAR v7.3.0 — Stability and concurrency safety"
```

### 9. Push

```bash
git push origin main
git push origin v7.3.0
```

### 10. Create GitHub Release

On https://github.com/zzzmada/permear/releases:

1. **Draft a new release**
2. Choose tag: `v7.3.0`
3. Title: `v7.3.0 — Stability and concurrency safety`
4. Description: paste the `[7.3.0]` section from `CHANGELOG.md`
5. Mark as **Latest release**
6. Publish

### 11. Pin ROADMAP.md as discussion starter

Open a GitHub Discussion titled "Roadmap to v10 — feedback wanted" pointing to ROADMAP.md. Both current users should be invited to comment.

---

## If something goes wrong

| Issue | Fix |
|---|---|
| Conflict markers re-appeared | Re-do steps 2-4. The wipe must be complete. |
| Tarball is missing files | Re-download. Count: `find . -type f \| wc -l` should be ~50 |
| Push rejected (non-fast-forward) | `git pull --rebase origin main` (shouldn't happen after step 2) |
