"""Exercise the guest admin fixture's CLI boundary without an NS8 guest.

Only the standalone task function is loaded: importing ns8_access.py would
create cluster users. The subprocess seam models api-cli's argparse login
interface; cluster actions and authentication itself are not integration-tested.
"""
import argparse
import ast
import contextlib
import io
import json
from pathlib import Path
import subprocess
import types
import unittest


SOURCE = Path(__file__).parent / 'admin' / 'ns8_access.py'


def load_task(run):
    tree = ast.parse(SOURCE.read_text())
    task = next(node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == 'task')
    namespace = {'json': json, 'subprocess': types.SimpleNamespace(run=run)}
    exec(compile(ast.Module(body=[task], type_ignores=[]), str(SOURCE), 'exec'), namespace)
    return namespace['task']


class Ns8AdminAccessCliTests(unittest.TestCase):
    def test_option_like_password_reaches_login_unchanged(self):
        for password in ('-synthetic-password', '--output', 'ordinary-password'):
            with self.subTest(password_kind='option' if password.startswith('-') else 'ordinary'):
                parsed_passwords = []
                calls = []

                def run(args, **kwargs):
                    calls.append(args)
                    if args[1] == 'login':
                        # Same login options as NS8 core 3.23.2 api-cli.
                        parser = argparse.ArgumentParser()
                        parser.add_argument('-u', '--username')
                        parser.add_argument('-p', '--password')
                        parser.add_argument('-o', '--output', action='store_true')
                        with contextlib.redirect_stderr(io.StringIO()):
                            try:
                                parsed = parser.parse_args(args[2:])
                            except SystemExit:
                                return subprocess.CompletedProcess(args, 2, '', 'hidden')
                        parsed_passwords.append(parsed.password)
                        return subprocess.CompletedProcess(args, 0, 'synthetic-ticket\n', '')
                    return subprocess.CompletedProcess(args, 0, '{"allowed": true}', '')

                task = load_task(run)
                self.assertEqual(task('module/fixture/open-admin', user='fixture-user',
                                      password=password), {'allowed': True})
                self.assertEqual(parsed_passwords, [password])
                self.assertEqual(calls[1][-2:], ['-t', 'synthetic-ticket'])

    def test_login_failure_still_stops_denial_case_without_disclosing_output(self):
        calls = []

        def run(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 1, 'sensitive-stdout', 'sensitive-stderr')

        task = load_task(run)
        with self.assertRaises(AssertionError) as caught:
            task('module/fixture/open-admin', user='fixture-user',
                 password='-synthetic-password', success=False)
        self.assertEqual(str(caught.exception), 'NS8 login failed (output hidden)')
        self.assertEqual(len(calls), 1)

    def test_denial_still_requires_action_failure_after_successful_login(self):
        for action_returncode in (0, 1):
            with self.subTest(action_returncode=action_returncode):
                def run(args, **kwargs):
                    if args[1] == 'login':
                        return subprocess.CompletedProcess(args, 0, 'synthetic-ticket', '')
                    return subprocess.CompletedProcess(args, action_returncode, '', '')

                task = load_task(run)
                if action_returncode == 0:
                    with self.assertRaisesRegex(AssertionError, 'unexpectedly authorized'):
                        task('module/fixture/open-admin', user='fixture-user',
                             password='-synthetic-password', success=False)
                else:
                    self.assertIsNone(task('module/fixture/open-admin', user='fixture-user',
                                           password='-synthetic-password', success=False))


if __name__ == '__main__':
    unittest.main()
