import os

def main():
    # This is a placeholder so GitHub Actions can run without crashing.
    # Next step: we’ll replace this with the real weekly generator.
    required = ["OPENAI_API_KEY", "GDRIVE_FOLDER_ID", "GOOGLE_SERVICE_ACCOUNT_JSON"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise SystemExit(f"Missing env vars: {', '.join(missing)}")
    print("Repo wired correctly. Next: implement weekly generation pipeline.")

if __name__ == "__main__":
    main()
