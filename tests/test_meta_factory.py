import pytest

from dodoclaw.meta.factory import create_meta_provider
from dodoclaw.meta.opendota import OpenDotaClient


def test_auto_without_stratz_uses_opendota():
    client = create_meta_provider("auto", stratz_api_token="")
    assert isinstance(client, OpenDotaClient)
    assert client.source_name == "opendota"


def test_force_opendota():
    client = create_meta_provider("opendota")
    assert client.source_name == "opendota"


def test_stratz_without_token_fallback():
    client = create_meta_provider(
        "stratz",
        stratz_api_token="",
        fallback_opendota=True,
    )
    assert isinstance(client, OpenDotaClient)


def test_stratz_without_token_no_fallback_raises():
    with pytest.raises(Exception):
        create_meta_provider(
            "stratz",
            stratz_api_token="",
            fallback_opendota=False,
        )


def test_stratz_with_token_constructs():
    from dodoclaw.meta.stratz import StratzClient

    client = create_meta_provider(
        "stratz",
        stratz_api_token="dummy-token-for-construct",
        fallback_opendota=False,
    )
    assert isinstance(client, StratzClient)
    assert client.source_name == "stratz"
