#!/usr/bin/env python3
# tsk/prefetch.py
"""
Prefetch Script for TSK Manager

This script runs before the main TSK Manager to prefetch necessary repositories.
It creates a GUI window with progress bars to track git clone operations for two repositories:
1. The recommended openpilot repository
2. The alternate openpilot repository

Features:
- Visual progress tracking with progress bars
- Directory cleanup before cloning
- Per-operation retry mechanism (up to 5 retries per operation)
- Automatic exit when operations complete or max retries reached
"""

# Standard library imports
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import List

# Third-party imports
import pyray as rl

# Local imports
from openpilot.system.ui.lib.application import gui_app
from tsk.common.env import (
  RECOMMENDED_OP_USER,
  RECOMMENDED_OP_BRANCH,
  RECOMMENDED_OP_DIR,
  ALTERNATE_OP_USER,
  ALTERNATE_OP_BRANCH,
  ALTERNATE_OP_DIR
)

# -------------------------------------------------------------------------
# Configuration Constants
# -------------------------------------------------------------------------

# Retry settings
MAX_RETRIES = 10       # Maximum number of retry attempts per operation
RETRY_DELAY = 10        # Seconds to wait between retry attempts

# -------------------------------------------------------------------------
# Git Clone Progress Tracker
# -------------------------------------------------------------------------

class GitCloneProgress:
  """
  Tracks the progress of a git clone operation.

  This class handles running a git clone command in a separate thread,
  parsing its output to track progress, and managing retries if the
  operation fails.

  Each instance represents one git clone operation with its own progress
  tracking and retry mechanism.
  """

  def __init__(self, command: List[str], title: str, target_dir: str = None):
    """
    Initialize a git clone progress tracker.

    Args:
        command: The git clone command as a list of strings.
        title: The title to display for this clone operation.
        target_dir: The target directory to delete before cloning (if provided).
    """
    # Command and identification
    self.command = command
    self.title = title
    self.target_dir = target_dir

    # Progress and status tracking
    self.progress = 0
    self.status = "Initializing..."
    self.completed = False
    self.failed = False

    # Process and thread management
    self.process = None
    self.thread = None

    # Retry mechanism
    self.retry_count = 0
    self.retry_needed = False
    self.retry_timer = 0

  def start(self):
    """
    Start the git clone process in a separate thread.

    This allows the GUI to remain responsive while the clone operation
    runs in the background.
    """
    self.thread = threading.Thread(target=self._run_process)
    self.thread.daemon = True  # Thread will exit when main program exits
    self.thread.start()

  def _run_process(self):
    """
    Run the git clone process and update progress.

    This method:
    1. Deletes the target directory if it exists
    2. Starts the git clone process
    3. Parses output to track progress
    4. Updates status based on completion or failure
    """
    try:
      # Step 1: Delete target directory if it exists
      if self.target_dir and os.path.exists(self.target_dir):
        self.status = f"Deleting existing directory: {self.target_dir}"
        try:
          shutil.rmtree(self.target_dir)
          self.status = f"Deleted directory: {self.target_dir}"
        except Exception as e:
          # If directory deletion fails, mark as failed and prepare for retry
          self.status = f"Error deleting directory: {str(e)}"
          self.failed = True
          self.retry_needed = True
          self.retry_timer = time.time()
          return

      # Step 2: Start the git clone process
      self.status = "Starting clone operation..."
      self.process = subprocess.Popen(
        self.command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1
      )

      # Step 3: Parse output to track progress
      for line in self.process.stdout:
        self._parse_progress(line)

      # Step 4: Check process completion status
      self.process.wait()
      if self.process.returncode == 0:
        # Success case
        self.progress = 100
        self.status = "Done"
        self.completed = True
      else:
        # Failure case - prepare for retry
        self.status = f"Failed with code {self.process.returncode}"
        self.failed = True
        self.retry_needed = True
        self.retry_timer = time.time()
    except Exception as e:
      # Handle any unexpected exceptions
      self.status = f"Error: {str(e)}"
      self.failed = True
      self.retry_needed = True
      self.retry_timer = time.time()

  def _parse_progress(self, line: str):
    """
    Parse git output to extract progress information.

    Git clone outputs progress in two main phases:
    1. "Receiving objects: x%" - Maps to 0-90% of our progress bar
    2. "Resolving deltas: x%" - Maps to 90-100% of our progress bar

    Args:
        line: A line of output from the git clone process
    """
    # Phase 1: Look for "Receiving objects: x%" pattern
    receiving_match = re.search(r'Receiving objects:\s+(\d+)%', line)
    if receiving_match:
      # Direct mapping for receiving objects phase
      self.progress = int(receiving_match.group(1))
      self.status = line.strip()
      return

    # Phase 2: Look for "Resolving deltas: x%" pattern
    resolving_match = re.search(r'Resolving deltas:\s+(\d+)%', line)
    if resolving_match:
      # Map resolving deltas from 0-100% to 90-100% of overall progress
      delta_progress = int(resolving_match.group(1))
      adjusted_progress = 90 + (delta_progress / 10)
      # Keep progress at least at current level (never go backwards)
      self.progress = max(self.progress, adjusted_progress)
      self.status = line.strip()
      return

    # Update status with current operation for any other informative lines
    if line.strip():
      self.status = line.strip()

  def reset(self):
    """
    Reset the progress tracker for a retry.

    This prepares the tracker for a fresh attempt after a failure.
    """
    self.progress = 0
    self.status = "Initializing retry..."
    self.completed = False
    self.failed = False
    self.process = None
    self.thread = None
    self.retry_needed = False

  def check_retry(self):
    """
    Check if it's time to retry and handle the retry if needed.

    This method:
    1. Checks if a retry is needed and possible
    2. Waits for the retry delay to elapse
    3. Increments retry count and starts a new attempt

    Returns:
        bool: True if a retry was initiated, False otherwise
    """
    if self.failed and self.retry_needed and self.retry_count < MAX_RETRIES:
      # Check if retry delay has elapsed
      if time.time() - self.retry_timer >= RETRY_DELAY:
        self.retry_count += 1
        self.reset()
        self.start()
        return True
    return False

# -------------------------------------------------------------------------
# Main Application
# -------------------------------------------------------------------------

class PrefetchApp:
  """
  GUI application to track git clone operations.

  This class creates a window with progress bars to visualize the status
  of git clone operations. It handles:
  1. Setting up and starting clone operations
  2. Rendering the UI with progress bars and status text
  3. Managing the application lifecycle
  4. Coordinating retries for failed operations
  """

  # UI Constants
  PROGRESS_BAR_HEIGHT = 100
  PROGRESS_BAR_WIDTH = 2000
  PADDING = 20
  FONT_SIZE = 80
  TITLE_FONT_SIZE = 120
  BAR_BG_COLOR = rl.Color(40, 40, 40, 255)      # Dark gray for progress bar background
  BAR_FG_COLOR = rl.Color(54, 77, 239, 255)     # Blue for progress bar foreground
  WHITE_TEXT_COLOR = rl.Color(255, 255, 255, 255)  # White for most text
  GRAY_TEXT_COLOR = rl.Color(100, 100, 100, 255)   # Dimmer gray for status text

  def __init__(self):
    """
    Initialize the prefetch application.

    Sets up the clone operations but doesn't start them yet.
    """
    self.initialize_operations()

  def initialize_operations(self):
    """
    Initialize or reset the clone operations.

    Creates GitCloneProgress instances for each repository we need to clone,
    but only if the target directories don't already exist. This handles all
    three possibilities gracefully: none, one, or both directories may exist.
    """
    self.clone_operations = []

    # Check if the recommended openpilot directory exists
    recommended_exists = os.path.exists(RECOMMENDED_OP_DIR)
    # Check if the alternate openpilot directory exists
    alternate_exists = os.path.exists(ALTERNATE_OP_DIR)

    # Only create operation for recommended repository if directory doesn't exist
    if not recommended_exists:
      self.clone_operations.append(
        GitCloneProgress(
          ["/usr/bin/git", "clone", "--progress",
           f"https://github.com/{RECOMMENDED_OP_USER}/openpilot.git",
           "-b", RECOMMENDED_OP_BRANCH, "--depth=1",
           "--recurse-submodules", RECOMMENDED_OP_DIR],
          f"{RECOMMENDED_OP_USER}/{RECOMMENDED_OP_BRANCH}",
          RECOMMENDED_OP_DIR  # Target directory to delete before cloning
        )
      )

    # Only create operation for alternate repository if directory doesn't exist
    if not alternate_exists:
      self.clone_operations.append(
        GitCloneProgress(
          ["/usr/bin/git", "clone", "--progress",
           f"https://github.com/{ALTERNATE_OP_USER}/openpilot.git",
           "-b", ALTERNATE_OP_BRANCH, "--depth=1",
           "--recurse-submodules", ALTERNATE_OP_DIR],
          f"{ALTERNATE_OP_USER}/{ALTERNATE_OP_BRANCH}",
          ALTERNATE_OP_DIR  # Target directory to delete before cloning
        )
      )

  def run(self):
    """
    Run the prefetch application with retry mechanism.

    This method:
    1. Initializes the window
    2. Starts clone operations
    3. Runs the main loop until completion or window close
    4. Handles cleanup and exit
    """
    # Step 1: Initialize window using gui_app (consistent with main.py)
    gui_app.init_window("TSK Prefetch")

    # Step 2: Start clone operations
    self.start_operations()

    # Step 3: Main loop
    while not rl.window_should_close():
      # Check for retries in each operation
      for op in self.clone_operations:
        op.check_retry()

      # Check if all operations are complete or have reached max retries
      all_done = True
      for op in self.clone_operations:
        if not op.completed and (not op.failed or op.retry_count < MAX_RETRIES):
          all_done = False
          break

      # Exit condition - all operations are either complete or have reached max retries
      if all_done:
        time.sleep(1)  # Show final state briefly
        break

      # Render the current frame
      self._render_frame()

    # Step 4: Cleanup and exit
    rl.close_window()

  def start_operations(self):
    """
    Start all clone operations.

    Initiates the background threads for all git clone operations.
    """
    for op in self.clone_operations:
      op.start()

  def _render_frame(self):
    """
    Render a single frame of the application.

    This method:
    1. Clears the background
    2. Draws the title
    3. For each operation:
       a. Draws the operation title with retry info
       b. Draws the progress bar
       c. Draws the progress percentage
       d. Draws the status text with retry countdown if applicable
    """
    # Step 1: Begin drawing and clear background
    rl.begin_drawing()
    rl.clear_background(rl.Color(0, 0, 0, 255))  # Black background

    # Step 2: Draw title
    title = "Prefetching"
    title_width = rl.measure_text_ex(gui_app.font(), title, self.TITLE_FONT_SIZE, 0).x
    rl.draw_text_ex(
      gui_app.font(),
      title,
      rl.Vector2((gui_app.width - title_width) // 2, self.PADDING),
      self.TITLE_FONT_SIZE,
      0,
      self.WHITE_TEXT_COLOR
    )

    # Step 3: Draw progress bars for each operation
    y_offset = self.PADDING * 3 + self.TITLE_FONT_SIZE * 2

    for i, op in enumerate(self.clone_operations):
      # Step 3a: Draw operation title with retry count if applicable
      title_text = op.title
      if op.retry_count > 0:
        title_text += f" (Retry {op.retry_count}/{MAX_RETRIES})"

      rl.draw_text_ex(
        gui_app.font(),
        title_text,
        rl.Vector2(self.PADDING, y_offset),
        self.FONT_SIZE,
        0,
        self.WHITE_TEXT_COLOR
      )
      y_offset += self.FONT_SIZE + self.PADDING

      # Step 3b: Draw progress bar background
      bar_x = (gui_app.width - self.PROGRESS_BAR_WIDTH) // 2
      bar_rect = rl.Rectangle(bar_x, y_offset, self.PROGRESS_BAR_WIDTH, self.PROGRESS_BAR_HEIGHT)
      rl.draw_rectangle_rec(bar_rect, self.BAR_BG_COLOR)

      # Step 3c: Draw progress bar foreground
      progress_width = (op.progress / 100.0) * self.PROGRESS_BAR_WIDTH
      progress_rect = rl.Rectangle(bar_x, y_offset, progress_width, self.PROGRESS_BAR_HEIGHT)
      rl.draw_rectangle_rec(progress_rect, self.BAR_FG_COLOR)

      # Step 3d: Draw progress percentage
      progress_text = f"{op.progress}%"
      text_width = rl.measure_text_ex(gui_app.font(), progress_text, self.FONT_SIZE, 0).x
      rl.draw_text_ex(
        gui_app.font(),
        progress_text,
        rl.Vector2(
          bar_x + (self.PROGRESS_BAR_WIDTH - text_width) // 2,
          y_offset + (self.PROGRESS_BAR_HEIGHT - self.FONT_SIZE) // 2
        ),
        self.FONT_SIZE,
        0,
        self.WHITE_TEXT_COLOR
      )

      # Step 3e: Draw status text with retry information if applicable
      status_y = y_offset + self.PROGRESS_BAR_HEIGHT + self.PADDING
      status_text = op.status

      # Add retry countdown or max retries reached message if applicable
      if op.failed and op.retry_needed and op.retry_count < MAX_RETRIES:
        countdown = max(0, int(RETRY_DELAY - (time.time() - op.retry_timer)))
        status_text += f" - Retrying in {countdown}s..."
      elif op.failed and op.retry_count >= MAX_RETRIES:
        status_text += f" - Max retries reached"

      rl.draw_text_ex(
        gui_app.font(),
        status_text,
        rl.Vector2(self.PADDING, status_y),
        self.FONT_SIZE,
        0,
        self.GRAY_TEXT_COLOR
      )

      # Update y_offset for next operation
      y_offset += self.PROGRESS_BAR_HEIGHT + self.PADDING * 2 + self.FONT_SIZE * 2

    # End drawing
    rl.end_drawing()

# -------------------------------------------------------------------------
# Main Entry Point
# -------------------------------------------------------------------------

def main():
  """
  Main function to run the prefetch application.

  This is the entry point when the script is executed directly.
  """
  app = PrefetchApp()
  app.run()

  # Exit with success code
  sys.exit(0)


if __name__ == "__main__":
  main()
