"""Credential lifecycle regression; only synthetic secrets in these fixtures."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'imageroot/pypkg'))
import vaultwarden_config as policy


class WorkerCredentialTests(unittest.TestCase):
    def test_second_update_preserves_verified_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory) / 'vaultwarden.env'
            token = Path(directory) / 'admin-worker.token'
            # Known real Argon2id vector, generated from a synthetic token.
            clear = 't' * 64
            hashed = '$argon2id$v=19$m=19456,t=2,p=1$jXKqQhjZLkgo5+O0dKS+QmNa2/Fq00DnaduYD1Uip04$LJpdv4Ye7oqKDzpv81LyBMQMecsyVpPzm0ouUb4hSQ4'
            # Generate with the actual packaged verifier's library to avoid a fake PHC.
            hashed = real_hash(clear)
            policy.private_write(env, 'SSO_CLIENT_SECRET=fixture\nADMIN_TOKEN=' + hashed + '\n')
            policy.private_write(token, clear + '\n')
            with patch.object(policy, 'argon2_hash', side_effect=AssertionError('unexpected rotation')):
                policy.ensure_worker_credential(env, token)
                before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in Path(directory).iterdir()}
                policy.ensure_worker_credential(env, token)
                after = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in Path(directory).iterdir()}
            self.assertEqual(before, after)
            self.assertEqual(policy.check_worker_credential(env, token), clear)


    def test_existing_admin_token_rejects_plausible_but_wrong_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            env, token = paths(directory)
            policy.private_write(env, 'ADMIN_TOKEN=' + real_hash('t' * 64) + '\n')
            policy.private_write(token, 'x' * 64 + '\n')
            with self.assertRaises(ValueError):
                policy.admin_token(env, token)

    def test_real_update_hook_is_idempotent(self):
        import contextlib
        import runpy
        import types
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as directory:
            env, token = paths(directory)
            policy.private_write(env, 'ADMIN_TOKEN=' + real_hash('t' * 64) + '\n')
            policy.private_write(token, 't' * 64 + '\n')
            policy.private_write(Path(directory) / 'settings.json', __import__('json').dumps({
                'host': 'vault.example.test', 'domain': 'ad.example.test', 'idp_module': 'idp1'}))
            agent = types.ModuleType('agent')
            agent.exclusive_file_lock = lambda _: contextlib.nullcontext()
            sso = types.ModuleType('vaultwarden_sso')
            sso.prepare = Mock()
            sso.task = Mock(return_value={'enforced': True, 'enabled': True,
                'policy_consumer_bound': True, 'policy_required': True,
                'policy_group_pinned': True, 'group_path': '/services_vaultwarden'})
            cwd = Path.cwd()
            try:
                os.chdir(directory)
                with patch.dict(sys.modules, {'agent': agent, 'vaultwarden_sso': sso}), \
                     patch.object(policy, 'argon2_hash', side_effect=AssertionError('update rotated credential')), \
                     patch('subprocess.run', return_value=types.SimpleNamespace(returncode=1)):
                    runpy.run_path(str(ROOT / 'imageroot/update-module.d/77access-policy'))
                    before = (env.read_bytes(), (Path(directory) / 'worker-credential.json').read_bytes())
                    runpy.run_path(str(ROOT / 'imageroot/update-module.d/77access-policy'))
                    self.assertEqual(before, (env.read_bytes(), (Path(directory) / 'worker-credential.json').read_bytes()))
            finally:
                os.chdir(cwd)

    def test_restart_hook_stops_incoherent_service_instead_of_restarting(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            env, token = paths(directory)
            policy.private_write(env, 'ADMIN_TOKEN=' + real_hash('t' * 64) + '\n')
            log = Path(directory) / 'calls'
            systemctl = Path(directory) / 'systemctl'
            systemctl.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALL_LOG"\nexit 0\n')
            systemctl.chmod(0o755)
            gate = Path(directory) / 'check-worker-credential'
            gate.write_text('#!/bin/sh\nexit 1\n')
            gate.chmod(0o755)
            result = subprocess.run(['bash', str(ROOT / 'imageroot/update-module.d/80restart')],
                cwd=directory, env=os.environ | {'PATH': directory + ':' + os.environ['PATH'], 'CALL_LOG': str(log)},
                capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('restart', log.read_text())
            self.assertIn('stop vaultwarden.service', log.read_text())

    def test_lifecycle_start_and_restore_gates_are_wired(self):
        service = (ROOT / 'imageroot/systemd/user/vaultwarden.service').read_text()
        self.assertIn('ExecStartPre=/usr/local/bin/runagent check-worker-credential', service)
        worker = (ROOT / 'imageroot/pypkg/vaultwarden_revoke.py').read_text()
        self.assertIn('check_worker_credential(env_path, token_path)', worker)
        restore = ROOT / 'imageroot/actions/restore-module/45credentials'
        self.assertTrue(restore.exists())
        self.assertTrue(os.access(restore, os.X_OK))
        self.assertIn('ensure_worker_credential', restore.read_text())
        update = (ROOT / 'imageroot/update-module.d/77access-policy').read_text()
        self.assertNotIn('rotate_worker_token', update)
        self.assertIn('ensure_worker_credential', update)
        self.assertIn('check_worker_credential', update)

    def test_wrong_hash_or_missing_legacy_token_fails_without_rotation(self):
        for mode in ('wrong-hash', 'missing-token'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                env, token = paths(directory)
                policy.private_write(env, 'ADMIN_TOKEN=' + real_hash('t' * 64) + '\n')
                if mode == 'wrong-hash':
                    policy.private_write(token, 'x' * 64 + '\n')
                before = env.read_bytes()
                with self.assertRaises(ValueError):
                    policy.ensure_worker_credential(env, token, hasher=real_hash)
                self.assertEqual(env.read_bytes(), before)
                with self.assertRaises(ValueError):
                    policy.check_worker_credential(env, token)

    def test_fault_after_canonical_commit_recovers_without_rotation(self):
        for boundary in ('before-env-replace', 'after-env-replace'):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as directory:
                env, token = paths(directory)
                policy.private_write(env, 'SSO_CLIENT_SECRET=fixture\nADMIN_TOKEN=' + 't' * 64 + '\n')
                original = policy.private_write
                def interrupt(path, text):
                    if Path(path) == env:
                        if boundary == 'after-env-replace':
                            original(path, text)
                        raise OSError('simulated power loss')
                    original(path, text)
                with patch.object(policy, 'private_write', side_effect=interrupt):
                    with self.assertRaises(OSError):
                        policy.ensure_worker_credential(env, token, hasher=real_hash)
                record = Path(directory) / 'worker-credential.json'
                committed = record.read_bytes()
                if boundary == 'before-env-replace':
                    with self.assertRaises(ValueError):
                        policy.check_worker_credential(env, token)
                with patch.object(policy, 'argon2_hash', side_effect=AssertionError('rotation')):
                    policy.ensure_worker_credential(env, token)
                self.assertEqual(record.read_bytes(), committed)
                self.assertEqual(policy.check_worker_credential(env, token), 't' * 64)
                self.assertIn('SSO_CLIENT_SECRET=fixture', env.read_text())

    def test_restore_old_cleartext_old_pair_and_new_backup(self):
        import shutil
        for backup in ('cleartext', 'hashed-pair', 'canonical'):
            with self.subTest(backup=backup), tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as restored:
                env, token = paths(source)
                clear = 't' * 64
                value = clear if backup == 'cleartext' else real_hash(clear)
                policy.private_write(env, 'ADMIN_TOKEN=' + value + '\n')
                if backup != 'cleartext':
                    policy.private_write(token, clear + '\n')
                if backup == 'canonical':
                    policy.ensure_worker_credential(env, token)
                # Exactly the module backup allowlist, not an invented full-state copy.
                includes = (ROOT / 'imageroot/etc/state-include.conf').read_text().splitlines()
                for entry in includes:
                    item = Path(source) / Path(entry).name
                    if item.exists():
                        shutil.copy2(item, Path(restored) / item.name)
                newenv, newtoken = paths(restored)
                policy.ensure_worker_credential(newenv, newtoken, hasher=real_hash)
                self.assertEqual(policy.check_worker_credential(newenv, newtoken), clear)
                self.assertNotIn(clear, newenv.read_text())

    def test_token_only_state_is_migrated_without_changing_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            env, token = paths(directory)
            policy.private_write(env, 'DOMAIN=https://fixture.test\n')
            policy.private_write(token, 't' * 64 + '\n')
            policy.ensure_worker_credential(env, token, hasher=real_hash)
            self.assertEqual(policy.check_worker_credential(env, token), 't' * 64)

    def test_explicit_rotation_and_schema_transition_only(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            env, token = paths(directory)
            policy.private_write(env, 'ADMIN_TOKEN=' + 't' * 64 + '\n')
            policy.ensure_worker_credential(env, token, hasher=real_hash)
            policy.ensure_worker_credential(env, token, hasher=real_hash, rotate=True)
            rotated = policy.check_worker_credential(env, token)
            self.assertNotEqual(rotated, 't' * 64)
            path = Path(directory) / 'worker-credential.json'
            data = json.loads(path.read_text())
            data['schema'] = 0
            policy.private_write(path, json.dumps(data))
            policy.ensure_worker_credential(env, token, hasher=real_hash)
            self.assertNotEqual(policy.check_worker_credential(env, token), rotated)

    def test_corrupt_record_and_projection_fail_closed(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            env, token = paths(directory)
            policy.private_write(env, 'ADMIN_TOKEN=' + 't' * 64 + '\n')
            policy.ensure_worker_credential(env, token, hasher=real_hash)
            record = Path(directory) / 'worker-credential.json'
            good_record, good_env = record.read_text(), env.read_text()
            for content in ('{}', '{', json.dumps({'schema': 999, 'token': 't' * 64, 'hash': real_hash('t' * 64)})):
                policy.private_write(record, content)
                with self.assertRaises(ValueError):
                    policy.check_worker_credential(env, token)
                with self.assertRaises(ValueError):
                    policy.ensure_worker_credential(env, token, hasher=real_hash)
            policy.private_write(record, good_record)
            policy.private_write(env, 'ADMIN_TOKEN=' + real_hash('x' * 64) + '\n')
            with self.assertRaises(ValueError):
                policy.check_worker_credential(env, token)
            policy.ensure_worker_credential(env, token)
            self.assertEqual(env.read_text(), good_env)
            record.chmod(0o644)
            with self.assertRaises(ValueError):
                policy.check_worker_credential(env, token)


def paths(directory):
    return Path(directory) / 'vaultwarden.env', Path(directory) / 'admin-worker.token'


def real_hash(token):
    # Tests use the same libargon2 ABI as production, with a fixed nonsecret salt.
    import ctypes
    import ctypes.util
    lib = ctypes.CDLL(ctypes.util.find_library('argon2') or 'libargon2.so.1')
    result = ctypes.create_string_buffer(512)
    secret = token.encode()
    salt = b'fixture-salt-1234'
    lib.argon2id_hash_encoded.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
        ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t,
        ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    rc = lib.argon2id_hash_encoded(2, 19456, 1, secret, len(secret), salt, len(salt), 32, result, len(result))
    assert rc == 0
    return result.value.decode()


if __name__ == '__main__':
    unittest.main()
