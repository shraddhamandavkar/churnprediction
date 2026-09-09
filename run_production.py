"""Production WSGI Server Launcher using Waitress (Cross-Platform / Windows & Linux)."""

import os
import sys
from app import app
from waitress import serve

PORT = int(os.environ.get("PORT", 5050))
HOST = os.environ.get("HOST", "0.0.0.0")
THREADS = int(os.environ.get("THREADS", 6))

if __name__ == "__main__":
  print("=" * 65)
  print("      CHURNGUARD PRODUCTION WSGI SERVER (WAITRESS)")
  print("=" * 65)
  print(f" * Serving host       : {HOST}")
  print(f" * Listening on port  : {PORT}")
  print(f" * Concurrency threads: {THREADS}")
  print(f" * Access URL         : http://127.0.0.1:{PORT}")
  print("=" * 65)
  print("Press CTRL+C to terminate the server.\n")

  try:
    serve(app, host=HOST, port=PORT, threads=THREADS)
  except KeyboardInterrupt:
    print("\n[INFO] Server stopped by user.")
    sys.exit(0)