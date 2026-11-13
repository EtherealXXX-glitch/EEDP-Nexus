# Bundled registration dependency

`tomli/` is Tomli 2.2.1 (MIT, Taneli Hukkinen), copied without modification
from pip's vendored pure-Python distribution. Upstream: https://github.com/hukkin/tomli
The MIT license is included. Used only when Python has no stdlib tomllib (e.g. WSL Python 3.10).
No network or package installation is required for this fallback.
