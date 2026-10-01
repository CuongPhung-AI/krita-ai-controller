"""
Krita AI Controller Plugin.
Enables programmatic AI drawing, canvas control, and live synchronization.
"""

from krita import Krita, DockWidgetFactory, DockWidgetFactoryBase
from .extension import AIControllerExtension
from .docker import AIControllerDocker

app = Krita.instance()

# Register Extension
app.addExtension(AIControllerExtension(app))

# Register Docker
app.addDockWidgetFactory(
    DockWidgetFactory(
        "ai_controller_docker",
        DockWidgetFactoryBase.DockPosition.DockRight,
        AIControllerDocker
    )
)
