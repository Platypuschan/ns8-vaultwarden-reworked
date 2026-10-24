"""Do not emit a domain-change event on each reconfiguration of a bound app."""
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]


class BindingTests(unittest.TestCase):
    def run_prepare(self, bound):
        tasks=types.ModuleType('agent.tasks')
        tasks.run=Mock(return_value={'exit_code':0,'output':json.dumps({
            'client_id':'vaultwarden1','client_secret':'test-only',
            'issuer':'https://sso.test/realms/ad.test'})})
        agent=types.ModuleType('agent')
        agent.tasks=tasks
        agent.bind_user_domains=Mock()
        agent.redis_connect=Mock()
        agent.get_bound_domain_list=Mock(return_value=bound)
        agent.assert_exp=lambda condition,message: self.assertTrue(condition,message)
        spec=importlib.util.spec_from_file_location('binding_test_sso',ROOT/'imageroot/pypkg/vaultwarden_sso.py')
        module=importlib.util.module_from_spec(spec)
        sys.path.insert(0,str(ROOT/'imageroot/pypkg'))
        try:
            with patch.dict(sys.modules,{'agent':agent,'agent.tasks':tasks}):
                spec.loader.exec_module(module)
                with patch.object(module.policy,'private_write'):
                    module.prepare({'host':'vault.test','domain':'ad.test','idp_module':'idp1'})
        finally:
            sys.path.pop(0)
        return agent,tasks

    def test_existing_binding_is_not_republished(self):
        agent,tasks=self.run_prepare(['ad.test'])
        agent.bind_user_domains.assert_not_called()
        self.assertEqual(tasks.run.call_args.kwargs['action'],'register-client')
        self.assertEqual(tasks.run.call_args.kwargs['data']['access_token_lifespan'],600)

    def test_new_binding_is_established_before_registration(self):
        agent,tasks=self.run_prepare([])
        agent.bind_user_domains.assert_called_once_with(['ad.test'],check=True)
        self.assertEqual(tasks.run.call_count,1)

if __name__=='__main__': unittest.main()
