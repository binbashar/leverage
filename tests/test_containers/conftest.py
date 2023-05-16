from unittest.mock import patch, Mock

import pytest


@pytest.fixture
def fake_os_user():
    with patch("os.getuid", Mock(return_value=1234)):
        with patch("os.getgid", Mock(return_value=5678)):
            yield
