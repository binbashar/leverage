from pynt import _pynt, main

import pytest
def test_foo():
    with pytest.raises(SystemExit):
          _pynt._create_parser().parse_args(["--file"]) # this line should throw SystemExit
