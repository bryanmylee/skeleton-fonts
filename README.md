# Installation

This script relies on FontForge.

## macOS

Install the packages required by FontForge.

```sh
brew install cmake glib pango gtk+3
```

Then, install FontForge.

```sh
brew install fontforge
```

Verify that FontForge was installed correctly.

```sh
python3 -c "import fontforge; print(fontforge.__file__)"
```

Add the directory path retrieved above to `.vscode/settings.json`. The
directory should end in `/site_packages`.

```json
{
  "python.analysis.extraPaths": [
    "/opt/homebrew/lib/python3.11/site-packages"
  ]
}
```

Allow the virtual environment to inherit system packages.

```sh
uv venv --system-site-packages
```
