"""Executa o BackupHub: `python -m backuphub`."""
import logging

from .app import create_app
from .config import Config


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = create_app()
    logging.getLogger("backuphub").info("BackupHub ouvindo em http://%s:%s", Config.HOST, Config.PORT)
    app.run(host=Config.HOST, port=Config.PORT, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
