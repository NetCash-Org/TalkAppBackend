#!/bin/bash
#uvicorn src.main:app --reload
#uvicorn src.main:app --reload
#uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}

#!/bin/bash
pip install -r requirements.txt
uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8002}