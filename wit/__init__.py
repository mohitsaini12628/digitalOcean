from wit import Wit

import sys
import logging

logging.getLogger(__name__).setLevel(logging.INFO)
logging.getLogger(__name__).propagate = False
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler = logging.StreamHandler(stream=sys.stdout)
handler.setFormatter(formatter)
logging.getLogger(__name__).addHandler(handler)
