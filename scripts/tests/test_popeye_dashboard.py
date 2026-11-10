import json
from pathlib import Path
import unittest

DASHBOARD = Path(__file__).resolve().parents[2] / 'kubernetes/apps/grafana/chart/provisioning/dashboards/files/popeye.json'


def panels(items):
    for item in items:
        yield item
        yield from panels(item.get('panels', []))


class PopeyeDashboardTest(unittest.TestCase):
    def test_current_value_panels_do_not_depend_on_historical_sampling(self):
        dashboard = json.loads(DASHBOARD.read_text())
        checked = 0
        for panel in panels(dashboard['panels']):
            if panel.get('type') not in ['gauge', 'stat']:
                continue
            for target in panel.get('targets', []):
                checked += 1
                with self.subTest(panel=panel.get('title', 'grade')):
                    self.assertTrue(target.get('instant'))
                    self.assertFalse(target.get('range', False))
        self.assertGreater(checked, 4)
