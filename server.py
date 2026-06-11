"""
Questra-Search 入口
"""
from app.main import app
import uvicorn
from app.config import PORT

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
