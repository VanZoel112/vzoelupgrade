# Pushing Changes With a Personal Access Token

The assistant cannot push directly to your repository, even if you share a token. Git credentials must stay on your local machine or a trusted runner. To push the changes yourself using a GitHub classic personal access token (PAT), follow these steps.

## 1. Configure the Remote URL With the Token
Replace `<TOKEN>` with your PAT and `<USER>/<REPO>` with the repository slug.

```bash
git remote set-url origin https://<TOKEN>@github.com/<USER>/<REPO>.git
```

You can also embed the token when cloning:

```bash
git clone https://<TOKEN>@github.com/<USER>/<REPO>.git
```

> ⚠️ Storing the token in the remote URL leaves it in your shell history and `.git/config`. Prefer using a credential helper or `gh auth login` when possible.

## 2. Stage, Commit, and Push
After verifying the changes:

```bash
git add <files>
git commit -m "Your commit message"
git push origin <branch>
```

If you have two-factor authentication enabled, the PAT acts as the password during the push.

## 3. Revoke or Rotate Tokens Regularly
- Visit https://github.com/settings/tokens
- Delete unused tokens
- Generate a new token if the existing one might be exposed

## 4. Use Environment Variables (Optional)
To avoid storing the token in plain text, export it temporarily:

```bash
export GITHUB_TOKEN=<TOKEN>
```

Then update the remote using shell expansion:

```bash
git remote set-url origin "https://${GITHUB_TOKEN}@github.com/<USER>/<REPO>.git"
```

Unset the variable when finished:

```bash
unset GITHUB_TOKEN
```

---
These steps let you keep full control over your credentials while still pushing the assistant-generated changes to GitHub.
