# py2app build options for the Kiro Gateway menu bar app.
#
# Build:
#   .venv/bin/python setup_menubar.py py2app
#
# Result:
#   dist/Kiro Gateway.app

from setuptools import setup

OPTIONS = {
    "argv_emulation": False,
    "includes": [
        "rumps",
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "kiro",
        "httpx",
        "loguru",
        "tiktoken",
        "anyio",
        "anyio._backends",
        "anyio._backends._asyncio",
        "email",
    ],
    "packages": ["anyio", "kiro"],
    "resources": [
        ".env",
        "main.py",
        "kiro/resources/menubar-ghost.png",
        "kiro/resources/menubar-ghost@2x.png",
        "kiro/resources/menubar-ghost-dim.png",
        "kiro/resources/menubar-ghost-dim@2x.png",
        "kiro/resources/eye.png",
        "kiro/resources/eye@2x.png",
        "kiro/resources/eye-slash.png",
        "kiro/resources/eye-slash@2x.png",
    ],
    "iconfile": "kiro/resources/AppIcon.icns",
    "plist": {
        "CFBundleName": "Kiro Gateway",
        "CFBundleDisplayName": "Kiro Gateway",
        "CFBundleIdentifier": "dev.kiro.gateway.menubar",
        "CFBundleVersion": "1.0.0",
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
    },
}

setup(
    app=["menubar.py"],
    name="Kiro Gateway",
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
