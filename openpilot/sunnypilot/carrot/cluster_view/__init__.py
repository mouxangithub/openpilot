"""cp cluster 的纯 2D HUD 在 sp onroad 主屏的 overlay（方案X：融合统一、不搞两套）。

保持 __init__ 扁平：真正 import ClusterOverlay 会拉到整个 UI 栈（Widget -> application ->
cffi），而无头的 cluster_overlay_renderer 冒烟测试只依赖纯逻辑 + pyray。因此这里不急切导入，
让 `import openpilot.sunnypilot.carrot.cluster_view.<submodule>` 在无头环境也能成立。
"""

__all__ = ["ClusterOverlay"]

# 延迟导出：from ...cluster_view import ClusterOverlay 仍可用，但只有真正访问才 import Widget 栈。
def __getattr__(name: str):
  if name == "ClusterOverlay":
    from openpilot.sunnypilot.carrot.cluster_view.cluster_overlay import ClusterOverlay
    return ClusterOverlay
  raise AttributeError(name)