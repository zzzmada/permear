"""
PERMEAR Organic Memory — inicializa o banco SQLite.
Executar uma vez no RPi4 via Developer Tools > Services > shell_command.init_memory_db
Idempotente: pode ser rodado múltiplas vezes sem efeitos colaterais.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.memory_db import init_db, stats
from permear_config import MEMORY_DB_PATH

init_db()
s = stats()
print(f"OK DB={MEMORY_DB_PATH} stats={s}")
