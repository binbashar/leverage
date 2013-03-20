import pytest
def test_foo():
    with pytest.raises(SystemExit):
          import argparse
          parser =  argparse.ArgumentParser()
          parser.add_argument('-f', '--file', help= "Build file",
                            metavar= "file", default= "build.py")
          parser.parse_args("[--file]") # this line should throw SystemExit
