"""Build frontend if needed, then run the integrated local server."""

from pathlib import Path
import os, subprocess, sys, shutil

if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    os.chdir(root)
    if not (root / "frontend/dist/index.html").exists():
        npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
        if not npm:
            sys.exit("Node.js LTS is required for the first frontend build.")
        if (
            not (root / "frontend/node_modules/.bin/vite.cmd").exists()
            and not (root / "frontend/node_modules/.bin/vite").exists()
        ):
            subprocess.run([npm, "ci"], cwd=root / "frontend", check=True)
        subprocess.run([npm, "run", "build"], cwd=root / "frontend", check=True)
    import uvicorn

    print("OMR Study: http://127.0.0.1:8000")
    uvicorn.run(
        "backend.main:app",
        host=os.getenv("OMR_HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", os.getenv("OMR_PORT", "8000"))),
    )
