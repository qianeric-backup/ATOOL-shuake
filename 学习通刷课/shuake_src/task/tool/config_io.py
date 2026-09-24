# -*- coding: utf-8 -*-
"""配置/题库导入导出（GUI 菜单使用）。

统一单文件 JSON 格式：
    {"kind": "config"|"bank"|"all", "version": 1, "exported_at": ...,
     "config": {...account_info...}, "bank": {"<缓存key>": {"value":..., "expire":...}}}

题库 = task/record/cache_*.pkl（ai_wen_da.Cache 的本地缓存，key 去掉
cache_ 前缀与 .pkl 后缀）。导入时过期条目跳过。
注意：config 含 API key 与学习通账号密码，导出文件请妥善保管。
"""
import glob
import json
import os
import pickle
import time

CONFIG_PATH = r'task/tool/account_info.json'
RECORD_DIR = r'task/record'


def _now():
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))


def export_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return {'kind': 'config', 'version': 1, 'exported_at': _now(),
                'config': json.load(f)}


def export_bank():
    bank = {}
    skipped = 0
    for p in glob.glob(os.path.join(RECORD_DIR, 'cache_*.pkl')):
        key = os.path.basename(p)[len('cache_'):-len('.pkl')]
        try:
            with open(p, 'rb') as f:
                cache_data = pickle.load(f)
            # value 必须可 JSON 序列化才能进导出文件
            json.dumps(cache_data.get('value'))
            bank[key] = cache_data
        except Exception:
            skipped += 1
    return {'kind': 'bank', 'version': 1, 'exported_at': _now(),
            'bank': bank, 'skipped_unserializable': skipped}


def export_all():
    payload = export_config()
    bank_payload = export_bank()
    payload['kind'] = 'all'
    payload['bank'] = bank_payload['bank']
    payload['skipped_unserializable'] = bank_payload['skipped_unserializable']
    return payload


def _apply_bank(bank):
    restored, skipped_expired = 0, 0
    now = time.time()
    for key, cache_data in (bank or {}).items():
        if not isinstance(key, str) or not key or '/' in key or '\\' in key \
                or '..' in key:
            continue
        try:
            expire = int(cache_data.get('expire', 0))
        except Exception:
            expire = 0
        if expire and expire < now:
            skipped_expired += 1
            continue
        try:
            with open(os.path.join(RECORD_DIR, f'cache_{key}.pkl'), 'wb') as f:
                pickle.dump({'value': cache_data.get('value'), 'expire': expire}, f)
            restored += 1
        except Exception:
            continue
    return restored, skipped_expired


def _apply_config(config):
    if not isinstance(config, dict) or not config:
        raise ValueError('文件中缺少有效的 config 数据')
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    return True


def import_data(payload, want='all'):
    """按文件内 kind 应用导入；want 为菜单语义（'config'|'bank'|'all'）。

    返回报告文本（供 GUI 消息框）。kind 与 want 不匹配时按实际 kind 处理。"""
    if not isinstance(payload, dict) or 'kind' not in payload:
        raise ValueError('不是本工具导出的备份文件（缺少 kind 字段）')
    kind = payload['kind']
    report = []
    if kind in ('config', 'all') and want in ('config', 'all'):
        _apply_config(payload.get('config'))
        report.append('配置已导入并写入 account_info.json')
    if kind in ('bank', 'all') and want in ('bank', 'all'):
        restored, expired = _apply_bank(payload.get('bank'))
        report.append(f'题库已导入：恢复 {restored} 条'
                      + (f'，跳过过期 {expired} 条' if expired else ''))
        if payload.get('skipped_unserializable'):
            report.append(f"（导出时已跳过不可序列化条目 {payload['skipped_unserializable']} 条）")
    if not report:
        raise ValueError(f'文件类型为「{kind}」，与所选导入目标（{want}）不符')
    if kind != want:
        report.append(f'注：文件实际类型为「{kind}」，已按实际类型导入')
    return '\n'.join(report)
