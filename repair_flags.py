"""Review switches: keep new behavior off until planner acceptance."""
import os


def enabled():
    return os.environ.get('WVB_ENABLE_REPAIRS') == '1'
