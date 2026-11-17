import asyncio

# 1. Impostiamo l'event loop per Python 3.14 prima che Streamlit si avvii
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

# 2. Avviamo Streamlit programmaticamente
from streamlit.web.cli import main
import sys

if __name__ == "__main__":
    sys.argv = ["streamlit", "run", "pagamenti.py"]
    main()
