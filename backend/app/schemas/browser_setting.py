from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictBool


class BrowserSettingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cloakbrowser_enabled: StrictBool


class BrowserSettingOut(BaseModel):
    engine: Literal["playwright", "cloakbrowser"]
    cloakbrowser_enabled: bool
    ready: bool
    cloakbrowser_installed: bool
    license_configured: bool
    humanize: bool
    proxy_configured: bool
    message: str
