# How to Push UI-Only Version to GitHub

Follow these steps to push only the UI files (without eye-tracking) to GitHub.

## Step 1: Verify Files

Make sure you have these files in your `eye-tracker` folder:

### ✅ Files to INCLUDE:
```
eye-tracker/
├── eye tracker/
│   ├── web_ui_standalone.py
│   └── web_ui/
│       ├── index.html
│       ├── styles.css
│       ├── script.js
│       ├── calling.html
│       ├── calling.css
│       ├── calling.js
│       ├── settings.html
│       ├── settings.css
│       ├── settings.js
│       ├── keyboard.html
│       ├── keyboard.css
│       ├── keyboard.js
│       ├── browsing_new.html
│       ├── browsing_new.css
│       └── browsing_new.js
├── requirements.txt
├── README.md
└── .gitignore
```

### ❌ Files to EXCLUDE (handled by .gitignore):
```
- modules/ (entire folder)
- face_landmarker.task
- main_web_ui.py
- web_ui_controller.py
- main.py
- __pycache__/
- .git/ (if exists)
```

## Step 2: Create GitHub Repository

1. Go to https://github.com
2. Click the "+" icon → "New repository"
3. Enter repository name (e.g., `assistive-ui`)
4. Add description: "Accessible web-based assistive interface"
5. Choose "Public" or "Private"
6. **DO NOT** initialize with README (we already have one)
7. Click "Create repository"

## Step 3: Initialize Git (if not already done)

Open terminal/command prompt in the `eye-tracker` folder:

```bash
cd path/to/eye-tracker
```

Check if git is already initialized:
```bash
git status
```

If you see "fatal: not a git repository", initialize it:
```bash
git init
```

## Step 4: Add Files to Git

```bash
# Add all files (gitignore will exclude unwanted files)
git add .

# Check what will be committed
git status
```

You should see:
- ✅ web_ui_standalone.py
- ✅ web_ui/ folder and its contents
- ✅ README.md
- ✅ requirements.txt
- ✅ .gitignore

You should NOT see:
- ❌ modules/
- ❌ face_landmarker.task
- ❌ main_web_ui.py
- ❌ web_ui_controller.py

## Step 5: Commit Changes

```bash
git commit -m "Initial commit: Assistive UI (standalone version)"
```

## Step 6: Connect to GitHub

Replace `<your-username>` and `<your-repo-name>` with your actual GitHub username and repository name:

```bash
git remote add origin https://github.com/<your-username>/<your-repo-name>.git
```

Example:
```bash
git remote add origin https://github.com/johndoe/assistive-ui.git
```

## Step 7: Push to GitHub

```bash
# For first push
git branch -M main
git push -u origin main
```

For subsequent pushes:
```bash
git push
```

## Step 8: Verify on GitHub

1. Go to your repository on GitHub
2. Check that only UI files are present
3. Verify README.md displays correctly
4. Confirm modules/ and eye-tracking files are NOT there

## Troubleshooting

### Problem: Eye-tracking files are being pushed

**Solution:**
```bash
# Remove from git tracking
git rm --cached -r "eye tracker/modules"
git rm --cached "eye tracker/face_landmarker.task"
git rm --cached "eye tracker/main_web_ui.py"
git rm --cached "eye tracker/web_ui_controller.py"

# Commit the removal
git commit -m "Remove eye-tracking files"

# Push again
git push
```

### Problem: "fatal: remote origin already exists"

**Solution:**
```bash
# Remove existing remote
git remote remove origin

# Add the correct remote
git remote add origin https://github.com/<your-username>/<your-repo-name>.git
```

### Problem: Authentication failed

**Solution:**
Use a Personal Access Token instead of password:
1. Go to GitHub → Settings → Developer settings → Personal access tokens
2. Generate new token with "repo" scope
3. Use token as password when pushing

Or use SSH:
```bash
git remote set-url origin git@github.com:<your-username>/<your-repo-name>.git
```

## Making Updates Later

After making changes to your code:

```bash
# Check what changed
git status

# Add changes
git add .

# Commit with a message
git commit -m "Description of changes"

# Push to GitHub
git push
```

## Quick Reference

```bash
# Clone your repo (for others)
git clone https://github.com/<your-username>/<your-repo-name>.git

# Pull latest changes
git pull

# Check status
git status

# View commit history
git log --oneline
```

## Success! 🎉

Your UI-only version is now on GitHub and ready to share!

Share your repository URL:
```
https://github.com/<your-username>/<your-repo-name>
```
