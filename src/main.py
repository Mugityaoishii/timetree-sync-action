import logging

from config import Config
from sync import sync

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    Config.validate()
    sync()


if __name__ == "__main__":
    main()
