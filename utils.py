# Author Dunin Ilya.
""" Module description """

from logging import StreamHandler, Formatter
from logging import DEBUG


def setup_logger(logger):
    logger.setLevel(DEBUG)
    console_hnd = StreamHandler()
    console_hnd.setLevel(DEBUG)
    console_hnd.setFormatter(Formatter('%(asctime)s %(module)s:%(lineno)d [%(levelname)s] %(message)s',
                                       datefmt='%Y-%m-%d %H:%M:%S'))
    logger.addHandler(console_hnd)
