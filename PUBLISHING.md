# How to publish this release (avoids git merge conflicts)

This file is for the **maintainer** (you). Not part of the public docs.

The previous publishing attempt failed because a git merge was attempted between
v5.7 (in main) and v7.2 (incoming). The merge created conflict markers that
made YAML invalid. We avoid this by **replacing**, not merging.

---

## Step-by-step publish

### 1. Clone fresh

On your local machine (not on the HA instance):

```bash
mkdir -p ~/projects && cd ~/projects
git clone https://github.com/zzzmada/permear permear-publish
cd permear-publish
```

You should be on `main` branch.

### 2. Verify current state (after your rollback)

```bash
git log --oneline -5
# Should show v5.7 at HEAD
```

### 3. Hard reset local main to remote main

This makes sure local main exactly matches what's on GitHub (after your rollback):

```bash
git fetch origin
git reset --hard origin/main
```

### 4. Delete everything except .git

```bash
# Inside permear-publish/
find . -maxdepth 1 ! -name '.git' ! -name '.' -exec rm -rf {} \;
ls -la
# Should show only .git
```

### 5. Extract the new tarball into the empty repo

```bash
cd ~/projects/permear-publish
tar -xzf ~/Downloads/permear-v7.2.tar.gz --strip-components=1
# --strip-components=1 strips the leading permear-v7.2/ directory
ls -la
# Should show README.md, CHANGELOG.md, scripts/, etc.
```

Alternatively (without --strip-components):

```bash
cd /tmp
tar -xzf ~/Downloads/permear-v7.2.tar.gz
cp -r /tmp/permear-v7.2/. ~/projects/permear-publish/
```

### 6. Verify no conflict markers

```bash
cd ~/projects/permear-publish
grep -rn "^<<<<<<<\|^=======$\|^>>>>>>>" . 2>/dev/null
# Should print nothing
```

### 7. Verify YAML and Python validate

```bash
# YAML check
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

# Python check
python3 -c "
import ast, os
for root, dirs, files in os.walk('scripts'):
    for f in files:
        if f.endswith('.py'):
            ast.parse(open(os.path.join(root, f)).read())
print('Python OK')
"
```

If anything errors here, **stop** and report back. Do not push.

### 8. Stage and commit

```bash
git status
# Review the list — should show all files as deleted + new (because we wiped and recopied)

git add -A
git status
# Now should show all changes as "modified" or "added"

git commit -m "v7.2.0: dual LLM path, automatic fallback, active forgetting

Major architecture changes from v5.7:
- Dual LLM path: interactive Gemini (chat/voice) + non-interactive DeepSeek (cycles)
- Automatic provider fallback via ai_task.generate_data + continue_on_error pattern
- Active forgetting: 30-day retention for patterns and pending items
- Shared library (lib/) eliminates ~700 lines of duplication
- Real-time error monitor with Telegram silence button
- Automation creation by chat via ai_task structured output
- /list_automations Telegram command

Breaking changes: JSON keys in English, AI Task entities required.
See MIGRATION.md for upgrade path from v5.x.
See ROADMAP.md for v7.3 and v8 plans (concurrency safety, SQLite)."
```

### 9. Tag the release

```bash
git tag -a v7.2.0 -m "PERMEAR v7.2.0 — Dual LLM path + automatic fallback + active forgetting"
```

### 10. Push

```bash
git push origin main
git push origin v7.2.0
```

### 11. Create GitHub Release

On https://github.com/zzzmada/permear/releases:

1. **Draft a new release**
2. Choose tag: `v7.2.0`
3. Title: `v7.2.0 — Dual LLM path + automatic fallback`
4. Description: paste the `[7.2.0]` section from `CHANGELOG.md`
5. Mark as **Latest release**
6. Publish

---

## If something goes wrong

### Conflict markers re-appeared

You probably didn't follow step 4 (wipe everything). Try again from step 2.

### Tarball is missing files

Re-download. Check `find . -type f | wc -l` should be ~46.

### Pre-push hook fails

If you have any pre-commit hooks, they may reject. Disable temporarily:

```bash
git commit --no-verify -m "..."
```

### Push rejected (non-fast-forward)

Don't force unless you're sure. Pull first:

```bash
git pull --rebase origin main
```

But there shouldn't be new commits on remote since your rollback.
