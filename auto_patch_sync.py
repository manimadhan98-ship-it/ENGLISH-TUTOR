import os
import sys
import json
import subprocess

PATCH_FILE = "patch.txt"
ENV_FILE   = ".env"

def load_env():
    if not os.path.exists(ENV_FILE): return {}
    env = {}
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env

def parse_patch_file(filepath):
    if not os.path.exists(filepath): return []
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    patches = []
    for sec in content.split("\nFILE:"):
        sec = sec.strip()
        if not sec: continue
        lines = sec.splitlines()
        filename = lines[0].strip()
        if filename.startswith("FILE:"): filename = filename[5:].strip()
        remaining = "\n".join(lines[1:])

        # ── OVERWRITE MODE (Forces write, ignores "file exists") ──
        if "<<<<<<< OVERWRITE" in remaining:
            body, _ = remaining.split(">>>>>>>", 1)
            body = body.split("<<<<<<< OVERWRITE", 1)[1].strip("\r\n")
            patches.append({"file": filename, "mode": "overwrite", "content": body})
            continue

        # ── CREATE MODE ──
        if "<<<<<<< CREATE" in remaining:
            body, _ = remaining.split(">>>>>>>", 1)
            body = body.split("<<<<<<< CREATE", 1)[1].strip("\r\n")
            patches.append({"file": filename, "mode": "create", "content": body})
            continue

        # ── FIND/REPLACE MODE ──
        for blk in remaining.split("<<<<<<< FIND"):
            if "=======" in blk and ">>>>>>>" in blk:
                find_part, rest = blk.split("=======", 1)
                replace_part, _ = rest.split(">>>>>>>", 1)
                find_str = find_part.strip("\r\n")
                replace_str = replace_part.strip("\r\n")
                if find_str:
                    patches.append({"file": filename, "mode": "replace", "find": find_str, "replace": replace_str})
    return patches

def apply_patches(patches, dry_run=False):
    if not patches: return 0
    count = 0
    for p in patches:
        tf = p["file"]
        mode = p.get("mode", "replace")

        # FORCE OVERWRITE
        if mode == "overwrite":
            if dry_run:
                print(f"🧪 Would OVERWRITE [{tf}]")
            else:
                with open(tf, "w", encoding="utf-8", newline="\n") as f:
                    f.write(p["content"] + "\n")
                print(f"✅ Overwritten [{tf}]")
            count += 1
            continue

        # CREATE (Skips if exists)
        if mode == "create":
            if os.path.exists(tf):
                print(f"⚠️  Already exists, skipped: {tf}")
                continue
            if dry_run:
                print(f"🧪 Would CREATE [{tf}]")
            else:
                with open(tf, "w", encoding="utf-8", newline="\n") as f:
                    f.write(p["content"] + "\n")
                print(f"✅ Created [{tf}]")
            count += 1
            continue

        # REPLACE
        if not os.path.exists(tf): continue
        with open(tf, "r", encoding="utf-8") as f:
            data = f.read().replace("\r\n", "\n")
        find = p["find"].replace("\r\n", "\n")
        replace = p["replace"].replace("\r\n", "\n")
        if find in data:
            if not dry_run:
                with open(tf, "w", encoding="utf-8", newline="\n") as f:
                    f.write(data.replace(find, replace, 1))
                print(f"✅ Patched [{tf}]")
            count += 1
    return count

def git_push(commit_msg="Update via auto-patch"):
    print("\n🚀 Pushing to GitHub...")
    env = load_env()
    user, repo, token = env.get("GITHUB_USER", ""), env.get("GITHUB_REPO", ""), env.get("GITHUB_TOKEN", "")
    branch = env.get("GITHUB_BRANCH", "main")

    if not user or not repo or not token:
        print("❌ .env missing GITHUB_USER / GITHUB_REPO / GITHUB_TOKEN.")
        return

    remote_url = f"https://{user}:{token}@github.com/{user}/{repo}.git"
    try:
        subprocess.run(["git", "add", "."], check=True)
        res = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if not res.stdout.strip():
            print("ℹ️  Nothing to commit.")
            return
        subprocess.run(["git", "commit", "-m", commit_msg], check=True)
        subprocess.run(["git", "push", remote_url, f"HEAD:{branch}"], check=True)
        print("🎉 Pushed! GitHub Pages live in ~20s.")
    except subprocess.CalledProcessError as e:
        print("❌ Git error:", e)

def main():
    print("1. Update + Push\n2. Update only\n3. Push only\n4. Dry-run")
    choice = input("👉 Choose [1/2/3/4]: ").strip()
    
    if choice in ("1", "2", "4"):
        patches = parse_patch_file(PATCH_FILE)
        if patches:
            apply_patches(patches, dry_run=(choice == "4"))
            if choice != "4":
                if input("🧹 Clear patch.txt? (Y/n): ").strip().lower() != "n":
                    open(PATCH_FILE, "w").close()
        else:
            print("ℹ️  patch.txt empty.")

    if choice in ("1", "3"):
        msg = input("\n📝 Commit message (Enter = default): ").strip() or "Update"
        git_push(msg)

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print("\n⚠️  Cancelled.")