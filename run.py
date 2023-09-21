import os
from hhbookingmanager.app import app

if __name__ == "__main__":
    app(
        host=os.environ.get("IP", ""),
        port=int(os.environ.get("PORT", "")),
        debug=False
    )
