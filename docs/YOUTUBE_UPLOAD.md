# YouTube upload (optional)

1. Google Cloud Console → new project → enable **YouTube Data API v3**.
2. OAuth consent screen (External) → add yourself as test user.
3. Credentials → Create OAuth client (Desktop) → download JSON.
4. `pip install google-api-python-client google-auth-oauthlib`
5. Set `YOUTUBE_CLIENT_SECRETS=/path/to/client_secrets.json` in `.env`.
6. `python -m science_studio upload <project-id> --privacy private|unlisted|public`

First run prints a URL for one-time consent; token cached in `token.json` (gitignored).
Quota: uploads ≈1600 units; default 10,000/day free.
Production (research→video→metadata→QA) never requires this.
