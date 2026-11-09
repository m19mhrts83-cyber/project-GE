import importlib.util
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('guard_raimo', ROOT / 'scripts/jarvis_kamiooya_guard_raimo.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class GuardRaimoTest(unittest.TestCase):
    def test_all_real_routes_require_server_proof_before_any_existing_action(self):
        source = next(ROOT.glob('215_kamiooya/**/WeStudy_API_secret_admin_upgrade.yaml'))
        original = yaml.safe_load(source.read_text())
        guarded = module.guard_definition(original)
        self.assertEqual(len(guarded['api']), 60)
        for before, after in zip(original['api'], guarded['api']):
            self.assertIn('__RAIMO_AUTH_GATEWAY_SECRET__', after['steps'][0]['check']['condition'])
            self.assertEqual(after['steps'][1:], before['steps'])
            self.assertEqual(after.get('output'), before.get('output'))
        # Deep-copy: do not silently rewrite the deployable source template.
        self.assertNotEqual(original['api'][0]['steps'][0], guarded['api'][0]['steps'][0])

    def test_pr_branch_does_not_create_vercel_previews(self):
        import json
        for path in ['vercel.json','apps/kamiooya-qa-web/vercel.json','apps/jarvis-dashboard/vercel.json','apps/trade-desk/vercel.json','apps/prompt-share/vercel.json']:
            config=json.loads((ROOT/path).read_text())
            enabled=config['git']['deploymentEnabled']
            # Git 連動を丸ごと止めたプロジェクト（false）も、このブランチのプレビューは作られない
            if enabled is not False:
                self.assertIs(enabled['codex/kamiooya-auth-offline-review'], False)

if __name__ == '__main__':
    unittest.main()

class ReleaseDefinitionTest(unittest.TestCase):
    def test_read_aliases_and_private_lookups_are_guarded(self):
        import sys
        sys.path.insert(0,str(ROOT/'scripts'))
        from jarvis_kamiooya_release_definition import release_definition
        source=next(ROOT.glob('215_kamiooya/**/WeStudy_API_secret_admin_upgrade.yaml'))
        result=release_definition(yaml.safe_load(source.read_text()))
        for route in result['api']:
            self.assertIn('__RAIMO_AUTH_GATEWAY_SECRET__',route['steps'][0]['check']['condition'])
        endpoints=[r['endpoint'] for r in result['api']]
        self.assertIn('POST /internal/read/comments',endpoints)
        self.assertIn('POST /internal/auth-user/user_id',endpoints)
        for route in result['api']:
            if route['name'] in ('listApprovedUsers','listPendingUsers'):
                self.assertFalse(any(s.get('check',{}).get('errorCode')=='security_maintenance' for s in route['steps']))
