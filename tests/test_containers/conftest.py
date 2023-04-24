from unittest.mock import patch, Mock

import pytest

from leverage.container import LeverageContainer


@pytest.fixture
def fake_os_user():
    with patch("os.getuid", Mock(return_value=1234)):
        with patch.object(LeverageContainer, "get_current_user_group_id", Mock(return_value=5678)):
            yield
