"""RuntimeDiagnostics peak_metric: one correlated peak frame per interval."""
import unittest

from openpilot.common.runtime_diagnostics import RuntimeDiagnostics


class TestPeakMetric(unittest.TestCase):
  def _collector(self, **kwargs):
    # list.append rejects kwargs, and the emit path swallows exceptions, so a
    # plain append would silently collect nothing. Wrap it.
    emitted = []
    diag = RuntimeDiagnostics('test', lambda *a, **k: emitted.append(k), interval=0.0, **kwargs)
    return diag, emitted

  def test_no_peak_without_metric(self):
    diag, emitted = self._collector()
    diag.record(context={'frame': True}, inference_ms=10.0, render_ms=2.0)
    self.assertNotIn('peak_sample', emitted[0])

  def test_peak_carries_full_correlated_frame(self):
    diag, emitted = self._collector(peak_metric='inference_ms')
    diag.record(context={'frame': True}, inference_ms=10.0, render_ms=2.0)
    diag.record(context={'frame': True}, inference_ms=5.0, render_ms=9.0)
    diag.record(context={'frame': True}, inference_ms=7.0, render_ms=1.0)
    peak = emitted[0]['peak_sample']
    # the whole record is owned: the render_ms of the peak frame is 2.0, not 9.0
    self.assertEqual(10.0, peak['metrics']['inference_ms'])
    self.assertEqual(2.0, peak['metrics']['render_ms'])
    self.assertEqual({'frame': True}, peak['context'])

  def test_peak_tracks_the_maximum(self):
    emitted = []
    diag = RuntimeDiagnostics('test', lambda *a, **k: emitted.append(k), interval=1.0,
                              peak_metric='inference_ms')
    diag.record(context={'id': 'a'}, inference_ms=3.0)
    diag.record(context={'id': 'b'}, inference_ms=8.0)
    # close the interval window so the accumulated peak is emitted
    diag.started -= diag.interval + 0.01
    diag.record(context={'id': 'c'}, inference_ms=5.0)
    self.assertEqual(1, len(emitted))
    self.assertEqual(8.0, emitted[0]['peak_sample']['metrics']['inference_ms'])
    self.assertEqual({'id': 'b'}, emitted[0]['peak_sample']['context'])

  def test_peak_resets_each_interval(self):
    diag, emitted = self._collector(peak_metric='inference_ms')
    diag.record(context={'id': 'a'}, inference_ms=8.0)
    first_peak = emitted[0]['peak_sample']
    diag.record(context={'id': 'b'}, inference_ms=3.0)
    second_peak = emitted[1]['peak_sample']
    self.assertEqual(3.0, second_peak['metrics']['inference_ms'])
    self.assertIsNot(first_peak, second_peak)

  def test_non_finite_peak_values_are_ignored(self):
    diag, emitted = self._collector(peak_metric='inference_ms')
    diag.record(context={'id': 'nan'}, inference_ms=float('nan'))
    self.assertNotIn('peak_sample', emitted[0])

  def test_missing_peak_metric_is_ignored(self):
    diag, emitted = self._collector(peak_metric='inference_ms')
    diag.record(context={'id': 'other'}, render_ms=1.0)
    self.assertNotIn('peak_sample', emitted[0])


if __name__ == '__main__':
  unittest.main()
