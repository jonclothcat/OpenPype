from . import PypeModule, ITrayAction


class SettingsAction(PypeModule, ITrayAction):
    """Action to show Setttings tool."""
    name = "settings"
    label = "Settings"

    def initialize(self, _modules_settings):
        # This action is always enabled
        self.enabled = True

        # User role
        # TODO should be changeable
        self.user_role = "developer"

        # Tray attributes
        self.settings_window = None

    def connect_with_modules(self, *_a, **_kw):
        return

    def tray_init(self):
        """Initialization in tray implementation of ITrayAction."""
        self.create_settings_window()

    def on_action_trigger(self):
        """Implementation for action trigger of ITrayAction."""
        self.show_settings_window()

    def create_settings_window(self):
        """Initializa Settings Qt window."""
        if self.settings_window:
            return
        from pype.tools.settings import MainWidget
        self.settings_window = MainWidget(self.user_role)

    def show_settings_window(self):
        """Show settings tool window.

        Raises:
            AssertionError: Window must be already created. Call
                `create_settings_window` before callint this method.
        """
        if not self.settings_window:
            raise AssertionError("Window is not initialized.")

        # Store if was visible
        was_visible = self.settings_window.isVisible()

        # Show settings gui
        self.settings_window.show()

        # Pull window to the front.
        self.settings_window.raise_()
        self.settings_window.activateWindow()

        # Reset content if was not visible
        if not was_visible:
            self.settings_window.reset()
