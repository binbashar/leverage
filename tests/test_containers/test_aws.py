import pytest
from unittest.mock import Mock, patch

from leverage._utils import ExitError
from leverage.container import AWSCLIContainer
from tests.test_containers import container_fixture_factory

SSO_CODE_MSG = """
Attempting to automatically open the SSO authorization page in your default browser.
If the browser does not open or you wish to use a different device to authorize this request, open the following URL:

https://device.sso.us-east-2.amazonaws.com/

Then enter the code:

TEST-CODE

"""


@pytest.fixture
def aws_container(muted_click_context):
    return container_fixture_factory(AWSCLIContainer)


@patch.object(AWSCLIContainer, "docker_logs", Mock(return_value=SSO_CODE_MSG))
def test_get_sso_code(aws_container):
    """
    Test that the get_sso_code method is able to extract correctly the SSO code from the `aws sso login` output.
    """
    assert aws_container.get_sso_code(Mock()) == "TEST-CODE"


@patch.object(AWSCLIContainer, "docker_logs", Mock(return_value="NO CODE!"))
@patch.object(AWSCLIContainer, "AWS_SSO_CODE_WAIT_SECONDS", 0)
def test_get_sso_code_exit_error(aws_container, propagate_logs, caplog):
    """
    Test that we don't get into an infinite loop if the SSO code never shows up.
    """
    with pytest.raises(ExitError, match="1"):
        aws_container.get_sso_code(Mock())
        assert caplog.messages[0] == "Get SSO code timed-out"


@patch.object(AWSCLIContainer, "get_sso_region", Mock(return_value="us-east-1"))
@patch.object(AWSCLIContainer, "get_sso_code", Mock(return_value="TEST-CODE"))
@patch.object(AWSCLIContainer, "docker_logs", Mock(side_effect=(SSO_CODE_MSG, "Logged in successfully!")))
@patch("webbrowser.open_new_tab")
def test_sso_login(mocked_new_tab, aws_container, fake_os_user, propagate_logs, caplog):
    """
    Test that we call the correct script and open the correct url.
    """
    test_link = "https://device.sso.us-east-1.amazonaws.com/?user_code=TEST-CODE"
    aws_container.sso_login()

    container_args = aws_container.client.api.create_container.call_args_list[0][1]
    # make sure we: point to the correct script
    assert container_args["command"] == "/home/leverage/scripts/aws-sso/aws-sso-login.sh"
    # the browser tab points to the correct code and the correct region
    assert mocked_new_tab.call_args[0][0] == "https://device.sso.us-east-1.amazonaws.com/?user_code=TEST-CODE"
    # and the fallback method is printed
    assert caplog.messages[0] == aws_container.FALLBACK_LINK_MSG.format(link=test_link)
