"""Accepted repairs are enabled by default; set the switch to 0 to roll back."""
import os


def enabled():
    return os.environ.get('WVB_ENABLE_REPAIRS', '1') == '1'
