"""Ponto de entrada WSGI (gunicorn): `gunicorn -w 1 --threads 16 backuphub.wsgi:app`.

Use apenas 1 worker: o agendador e a fila de jobs rodam dentro do processo.
"""
import logging

from .app import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
