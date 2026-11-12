"""get_active_globals_grouped：一次查询分组（语义与逐类型查询一致）"""

import pytest

from app.models.global_variable import GlobalVariable
from app.services import global_variable_service


async def _seed(db, **kwargs) -> GlobalVariable:
    defaults = dict(name="token", value="v", type="header", enabled=True, domain="")
    defaults.update(kwargs)
    _seed._counter += 1
    var = GlobalVariable(id=_seed._counter, **defaults)
    db.add(var)
    await db.commit()
    await db.refresh(var)
    return var


_seed._counter = 0


async def test_grouped_matches_individual_queries(db):
    await _seed(db, name="X-Token", value="t1", type="header", domain="a.com")
    await _seed(db, name="env", value="prod", type="variable", domain="")
    await _seed(db, name="sid", value="s1", type="localStorage", domain="a.com")
    await _seed(db, name="session", value="c1", type="cookie", domain="a.com")
    await _seed(
        db, name="session", value="c2", type="cookie", domain=""
    )  # 未绑定域，全局生效
    await _seed(db, name="X-Off", value="x", type="header", enabled=False)  # 停用不注入

    headers, gvars, storage, cookies = (
        await global_variable_service.get_active_globals_grouped(
            db, "https://admin.a.com/login"
        )
    )
    assert headers == {"X-Token": "t1"}
    assert gvars == {"env": "prod"}
    assert storage == {"sid": "s1"}
    # 域名配置覆盖通用同名 Cookie，避免请求携带两个不同 session。
    assert [(c["name"], c["value"], c["domain"]) for c in cookies] == [
        ("session", "c1", "a.com")
    ]


async def test_grouped_unbound_cookie_uses_start_host(db):
    await _seed(db, name="sid", value="s9", type="cookie", domain="")
    _, _, _, cookies = await global_variable_service.get_active_globals_grouped(
        db, "http://app.b.com:8080/path"
    )
    assert cookies == [
        {"name": "sid", "value": "s9", "domain": "app.b.com", "path": "/"}
    ]


async def test_grouped_subdomain_match(db):
    await _seed(db, name="X-Token", value="t", type="header", domain="example.com")
    headers, _, _, _ = await global_variable_service.get_active_globals_grouped(
        db, "https://api.example.com"
    )
    assert headers == {"X-Token": "t"}
    # 无关域名不匹配
    headers2, _, _, _ = await global_variable_service.get_active_globals_grouped(
        db, "https://other.org"
    )
    assert headers2 == {}


async def test_specific_domain_always_beats_generic_regardless_of_creation_order(db):
    await _seed(db, name="authorization", value="specific", domain="api.example.com")
    await _seed(db, name="Authorization", value="parent", domain="example.com")
    await _seed(db, name="AUTHORIZATION", value="generic", domain="")
    headers, _, _, _ = await global_variable_service.get_active_globals_grouped(
        db, "https://api.example.com:8443/page"
    )
    assert headers == {"authorization": "specific"}
    headers, _, _, _ = await global_variable_service.get_active_globals_grouped(
        db, "https://evil-example.com"
    )
    assert headers == {"AUTHORIZATION": "generic"}


async def test_cookie_without_target_url_is_not_injected(db):
    await _seed(db, name="session", type="cookie", domain="")
    assert (await global_variable_service.get_active_globals_grouped(db, ""))[3] == []
