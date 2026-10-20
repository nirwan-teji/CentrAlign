"""Start the CentrAlign live observation console."""
import uvicorn
import os


if __name__ == "__main__":
    uvicorn.run("server.app:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=False)
