"""Network-free tests for OVH Compose preflight (including negative checks)."""
import copy
import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / 'check_compose.py'
spec = importlib.util.spec_from_file_location('ovh_compose', MODULE)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def sample():
    return {
        'services': {
            'db': {
                'environment': {'POSTGRES_PASSWORD': 'example-long-test-only-' * 3},
                'networks': {'private': None},
            },
            'api': {
                'environment': {
                    'OIP_LEGACY_API_KEY_ENABLED': 'false',
                    'OIP_MANUAL_COLLECTION_ENABLED': 'false',
                    'OIP_TOR_COLLECTION_ENABLED': 'false',
                    'OIP_API_KEY': 'example-secure-test-only-' * 3,
                },
                'networks': {'private': None},
                'read_only': True,
                'cap_drop': ['ALL'],
            },
            'gateway': {
                'ports': [{'host_ip': '127.0.0.1', 'published': '8000',
                           'target': 8080, 'protocol': 'tcp'}],
                'networks': {'private': None, 'ingress': None},
                'read_only': True,
                'cap_drop': ['ALL'],
            },
        },
        'networks': {'onion-intelligence-platform_private': {'internal': True},
                     'onion-intelligence-platform_ingress': {'internal': False}},
    }


class OvhComposePolicyTest(unittest.TestCase):
    def test_valid_private_core(self):
        checker.validate(sample())

    def test_fail_closed_cases(self):
        def mutate_public_ip(obj):
            obj['services']['gateway']['ports'][0]['host_ip'] = '0.0.0.0'
        def mutate_db_port(obj):
            obj['services']['db']['ports'] = [{'published': '5432', 'target': 5432}]
        def mutate_worker_without_profile(obj):
            obj['services']['queue_worker'] = {'networks': {'private': None}}
        def mutate_manual_gate(obj):
            obj['services']['api']['environment']['OIP_MANUAL_COLLECTION_ENABLED'] = 'true'
        def mutate_legacy_auth(obj):
            obj['services']['api']['environment']['OIP_LEGACY_API_KEY_ENABLED'] = 'true'
        def mutate_docker_sock(obj):
            obj['services']['api']['volumes'] = ['/var/run/docker.sock:/var/run/docker.sock']
        def mutate_weak_secret(obj):
            obj['services']['db']['environment']['POSTGRES_PASSWORD'] = 'example'
        def mutate_private_network(obj):
            obj['networks']['onion-intelligence-platform_private']['internal'] = False
        def mutate_new_service(obj):
            obj['services']['unexpected'] = {}
        def mutate_host_mode(obj):
            obj['services']['gateway']['network_mode'] = 'host'
        def mutate_api_disk(obj):
            obj['services']['api']['read_only'] = False
        mutations = [mutate_public_ip, mutate_db_port, mutate_worker_without_profile,
                     mutate_manual_gate, mutate_legacy_auth, mutate_docker_sock,
                     mutate_weak_secret, mutate_private_network, mutate_new_service,
                     mutate_host_mode, mutate_api_disk]
        for mutation in mutations:
            with self.subTest(case=mutation.__name__):
                obj = copy.deepcopy(sample())
                mutation(obj)
                with self.assertRaises(ValueError):
                    checker.validate(obj)

    def test_safe_tor_services_may_be_defined_but_not_active(self):
        obj = sample()
        obj['services']['tor'] = {'profiles': ['tor']}
        obj['services']['collector'] = {'profiles': ['tor']}
        obj['services']['queue_worker'] = {'profiles': ['tor']}
        checker.validate(obj)


if __name__ == '__main__':
    unittest.main()
