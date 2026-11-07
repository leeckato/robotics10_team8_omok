"""설정 파일(config.yaml) 읽기/쓰기"""
import os
import copy

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATH = os.path.join(ROOT, 'config.yaml')


def project_path(rel):
    """프로젝트 폴더 기준 상대경로 -> 절대경로"""
    return rel if os.path.isabs(rel) else os.path.join(ROOT, rel)


def load_config(path=DEFAULT_PATH):
    with open(path, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    cfg['_path'] = path
    return cfg


def save_config(cfg, path=None):
    path = path or cfg.get('_path', DEFAULT_PATH)
    data = copy.deepcopy(cfg)
    data.pop('_path', None)
    with open(path, 'w', encoding='utf-8') as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def board_geometry(cfg):
    b = cfg['board']
    return b['n'], b['cell'], b['margin']


def warp_size(cfg):
    n, cell, margin = board_geometry(cfg)
    return 2 * margin + cell * (n - 1)
