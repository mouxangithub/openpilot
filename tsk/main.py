#!/usr/bin/env python3
# tsk/main.py
import sys

import pyray as rl

from openpilot.system.ui.lib.application import gui_app
from tsk.common.env import is_calvins_c3x
from tsk.reboot_menu.ui import RebootMenuUI
from tsk.tools_menu.ui import ToolsMenuUI
from tsk.ui.header import Header
from tsk.ui.layout import Theme


class TSKManager:
  """Manages the TSK Manager UI, switching between menus."""

  def __init__(self):
    """Initializes the TSK Manager."""
    self.current_menu = Theme.menu_tools
    self.header = Header()
    self.tools_menu = ToolsMenuUI()
    self.reboot_menu = RebootMenuUI()

  def render(self, rect: rl.Rectangle):
    """Renders the current menu within the given rectangle."""

    new_menu = self.header.render(rect, self.current_menu)
    if new_menu is not None:
      self.current_menu = new_menu

    menu_rect = rl.Rectangle(rect.x, rect.y + self.header._calculate_height(), rect.width,
                             rect.height - self.header._calculate_height())

    if self.current_menu == Theme.menu_tools:
      self.tools_menu.render(menu_rect)
    elif self.current_menu == Theme.menu_reboot:
      self.reboot_menu.render(menu_rect)
    return True


def setup_environment():
  """Performs initial environment setup, such as enabling SSH."""
  if is_calvins_c3x():
    with open("/data/params/d/GithubUsername", "w") as f:
      f.write("calvinpark")
    with open("/data/params/d/GithubSshKeys", "w") as f:
      f.write("ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD30Dz8yY3n1DchzsPbuuWMXMBtyeW2Yh5aOjrjLSvUBjqs9OoPrPfOMAPiaKqE6EfEcjV90He9A6q7OywTy5kTD6JsjjoULJKHiGbDdQlclXE2fO/wTnmxPO9yjdDJqiFrPsSGbT/4R78TVUUkEwD+6DcDGtJd7hHQ/GQCWn78kZ/UsZqcukGjhuwI98gOnIOmX3ui2W6/2NrP3IH7GJWnIvDIHafHYwnRkNU7WQ5zyiUw2GX65dTrXt0pDpX/nYp0qjwORf91DTZCg6fimdUo2WAmhYXnQb66IKESpNVfIVA8L0PRNkSepc3RARX0bPgqYGj6TLy9s87UT11mq/ASuIo9IVYWt6okYvloQcwrX6uxKsGutXouXDraxP648s1ErM6BC3tOOagay19cZdQl53k0CZbkIXODlpM/QaW7MdagH7PVzlGGIuHohDAe3M/ltJjRmRfdj89cCGusBlFB5RuLZpzYskp353NZ1qxhL086Mfyg0bBdDK+CGLJ7bY0=\n"
              "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILXx7npi7/QYSOu2Z0Bhldtey4L2nxEyZKYQY/BIHdak")
    with open("/data/params/d/SshEnabled", "w") as f:
      f.write("1")
    with open("/data/params/d/HasAcceptedTerms", "w") as f:
      f.write("2")
    with open("/data/params/d/CompletedTrainingVersion", "w") as f:
      f.write("0.2.0")


def main():
  """Main function to initialize and run the TSK Manager."""

  setup_environment()

  gui_app.init_window("TSK Manager")
  tskm = TSKManager()

  while not rl.window_should_close():
    rl.begin_drawing()
    rl.clear_background(rl.BLACK)

    tskm.render(rl.Rectangle(0, 0, gui_app.width, gui_app.height))

    rl.end_drawing()

  rl.close_window()
  sys.exit(0)  # Necessary for macOS


if __name__ == "__main__":
  main()
