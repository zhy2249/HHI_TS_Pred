#!/usr/bin/env python3
"""Lossless bounded storage for rule-lab derived schedules, never input .bin files.

pack-complete only packs schedules whose evaluation has a valid complete receipt.
archive-interrupted packs quarantined derived .pred/.partial files. restore accepts
one archived schedule path. Archive hashes are verified before removing plaintext.
"""
import argparse
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import time

CHUNK = 1024 * 1024


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        while block := f.read(CHUNK):
            h.update(block)
    return h.hexdigest()


def save(path, data):
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(data, indent=2) + '\n')
    temp.replace(path)


def pack(path, limit_bytes, expected=None):
    if path.is_symlink() or not path.name.endswith(('.pred', '.pred.partial')):
        raise ValueError('Only regular derived prediction files may be packed')
    archive = path.with_name(path.name + '.gz')
    if archive.exists():
        raise ValueError('Archive already exists; do not overwrite it')
    initial = path.stat()
    temp = archive.with_name(archive.name + '.packing')
    h = hashlib.sha256()
    try:
        with path.open('rb') as src, temp.open('wb') as dst:
            with gzip.GzipFile(filename='', mode='wb', fileobj=dst, compresslevel=1, mtime=0) as gz:
                while block := src.read(CHUNK):
                    h.update(block)
                    gz.write(block)
                    if dst.tell() > limit_bytes:
                        raise ValueError('Compressed archive size limit reached')
            dst.flush()
            os.fsync(dst.fileno())
        if temp.stat().st_size > limit_bytes:
            raise ValueError('Compressed archive size limit reached')
        digest = h.hexdigest()
        if expected is not None and digest != expected:
            raise ValueError('Plaintext SHA differs from completed schedule receipt')
        check = hashlib.sha256()
        with gzip.open(temp, 'rb') as f:
            while block := f.read(CHUNK):
                check.update(block)
        final = path.stat()
        if (initial.st_ino, initial.st_size, initial.st_mtime_ns) != (final.st_ino, final.st_size, final.st_mtime_ns):
            raise ValueError('Source changed while packing; plaintext preserved')
        if check.hexdigest() != digest:
            raise ValueError('Archive round-trip hash mismatch')
        record = dict(file=str(path), archive=str(archive), uncompressed_bytes=initial.st_size,
                      compressed_bytes=temp.stat().st_size, plaintext_sha256=digest,
                      archive_sha256=sha(temp), round_trip_verified=True)
        temp.replace(archive)
        save(archive.with_name(archive.name + '.storage.json'), record)
        path.unlink()
        # Hint away only the derived archive's cache; no global cache operation.
        if hasattr(os, 'posix_fadvise'):
            with archive.open('rb') as f:
                os.posix_fadvise(f.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)
        return record
    finally:
        temp.unlink(missing_ok=True)


def pack_completed(root, limit_bytes):
    records = []
    for done in sorted((root / 'evaluation').glob('*/done.json')):
        data = json.loads(done.read_text())
        key = data['task']['key']
        path = root / 'schedules' / (key + '.pred')
        if not path.exists():
            continue
        meta = json.loads(path.with_suffix('.json').read_text())
        if not data['complete'] or not data['footer']['complete']:
            raise ValueError('Incomplete evaluation')
        if data['request']['schedule_sha256'] != meta['schedule_sha256']:
            raise ValueError('Evaluation and schedule fingerprint mismatch')
        if sha(done.parent / 'corpus.jsonl.gz') != data['data_sha256']:
            raise ValueError('Completed evaluation data hash mismatch')
        records.append(pack(path, limit_bytes, meta['schedule_sha256']))
        print('PACKED', key, records[-1]['uncompressed_bytes'], '->', records[-1]['compressed_bytes'], flush=True)
    return records


def restore(archive):
    if archive.is_symlink() or not archive.name.endswith('.pred.gz'):
        raise ValueError('Provide a derived .pred.gz archive')
    record = json.loads(archive.with_name(archive.name + '.storage.json').read_text())
    if sha(archive) != record['archive_sha256']:
        raise ValueError('Archive SHA mismatch')
    target = archive.with_suffix('')
    if target.exists():
        raise ValueError('Plaintext exists; refusing overwrite')
    temp = target.with_name(target.name + '.restoring')
    h = hashlib.sha256()
    try:
        with gzip.open(archive, 'rb') as src, temp.open('wb') as dst:
            while block := src.read(CHUNK):
                h.update(block)
                dst.write(block)
        if h.hexdigest() != record['plaintext_sha256'] or temp.stat().st_size != record['uncompressed_bytes']:
            raise ValueError('Restored schedule identity mismatch')
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['pack-complete', 'archive-interrupted', 'restore'])
    p.add_argument('--root', type=Path)
    p.add_argument('--archive', type=Path)
    p.add_argument('--max-archive-mib', type=int, default=256)
    p.add_argument('--watch', action='store_true', help='Pack newly completed streams until the evaluation index is complete')
    p.add_argument('--interval', type=float, default=30)
    a = p.parse_args()
    if a.action == 'restore':
        if a.archive is None:
            p.error('--archive required')
        restore(a.archive)
        return
    if a.root is None or a.max_archive_mib <= 0 or a.interval <= 0:
        p.error('--root and positive archive limit required')
    with (a.root / '.schedule_storage.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        limit = a.max_archive_mib * CHUNK
        receipt = a.root / ('storage_' + a.action + '_' + str(time.time_ns()) + '.json')
        if a.action == 'pack-complete':
            records = []
            while True:
                records.extend(pack_completed(a.root, limit))
                index = a.root / 'evaluation' / 'dataset_index.json'
                complete = index.exists() and json.loads(index.read_text()).get('complete', False)
                save(receipt, dict(records=records, count=len(records), evaluation_complete=complete,
                                   uncompressed_bytes=sum(x['uncompressed_bytes'] for x in records),
                                   compressed_bytes=sum(x['compressed_bytes'] for x in records)))
                if not a.watch or complete:
                    break
                time.sleep(a.interval)
        else:
            if a.watch:
                p.error('--watch only applies to pack-complete')
            paths = sorted(p for p in (a.root / 'interrupted_schedules').rglob('*')
                           if p.is_file() and p.name.endswith(('.pred', '.pred.partial')))
            records = [pack(path, limit) for path in paths]
        save(receipt, dict(records=records, count=len(records),
                           uncompressed_bytes=sum(x['uncompressed_bytes'] for x in records),
                           compressed_bytes=sum(x['compressed_bytes'] for x in records)))
        print('PACKED FILES', len(records), 'receipt', receipt)


if __name__ == '__main__':
    main()
