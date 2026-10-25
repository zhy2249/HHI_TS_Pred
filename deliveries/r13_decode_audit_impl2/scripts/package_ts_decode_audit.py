#!/usr/bin/env python3
"""Build/verify a local, relocatable R13 audit tar.gz. No upload or downloads.
Only explicit program/scripts/docs and manifest-listed bitstreams are packed.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import ts_decode_score_audit as audit

FILES=('ts_decode_score_audit.py','ts_audit_stats.py','test_ts_decode_score_audit_runtime.py',
       'test_ts_decode_score_audit.py','package_ts_decode_audit.py')


def build(args):
    manifest,decoder=audit.inspect_manifest(args.manifest)
    if args.output.exists():raise ValueError('Archive exists; choose a new path')
    base=args.manifest.resolve().parent
    pairs=manifest['pairs'] if args.pairs=='all' else [p for p in manifest['pairs'] if p['pair_id'] in args.pairs.split(',')]
    if not pairs or (args.pairs!='all' and {p['pair_id'] for p in pairs}!=set(args.pairs.split(','))):raise ValueError('Unknown pair selection')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ts-audit-package-') as tmp:
        root=Path(tmp)/'r13_decode_audit';root.mkdir();(root/'bin').mkdir();(root/'scripts').mkdir();(root/'docs').mkdir()
        shutil.copy2(decoder,root/'bin/DecoderAppAudit')
        selected=copy.deepcopy(manifest);selected['pairs']=copy.deepcopy(pairs)
        # Historical development paths are not portable payload requirements.
        selected.pop('validation_manifest',None)
        for pair in selected['pairs']:
            for origin,stream in pair['origins'].items():
                source=audit.resolved(base,stream['path'])
                rel=Path('streams')/pair['pair_id']/(origin.replace('-','_')+'.bin')
                destination=root/rel;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,destination)
                if audit.sha(destination)!=stream['sha256']:raise ValueError('Packaged stream hash mismatch')
                stream['path']=rel.as_posix()
        selected['decoder']['path']='bin/DecoderAppAudit'
        selected['delivery']=dict(channel='local_archive',remote_binary_published=False,paths='relative to this manifest')
        audit.save(root/'manifest.json',selected)
        build_info=audit.read_json(base/'build_info.json')
        build_info.pop('validation_build_info',None)
        build_info['packaged_scripts_sha256']={name:audit.sha(Path(__file__).with_name(name)) for name in FILES}
        audit.save(root/'build_info.json',build_info)
        for name in FILES:shutil.copy2(Path(__file__).with_name(name),root/'scripts'/name)
        repo=Path(__file__).resolve().parent.parent
        for name in ('TS_Predictor_Dual_Decoder_Audit_Implementation.md','TS_Predictor_Dual_Stream_Decoder_Audit_Requirements.md','TS_Predictor_Dual_Decoder_Audit_Schema.md'):
            source=repo/'docs/experiments'/name
            if source.exists():shutil.copy2(source,root/'docs'/name)
        (root/'README.md').write_text('''# R13双来源评分审计 impl2

Linux x86_64，最低SSE4.1；Python 3.10+标准库；不需要GPU或原始YUV。
依赖和源版本见build_info.json，完整性见SHA256SUMS，源代码由对应Git提交提供。
从本目录运行，无重建视频，不启动EncoderApp：

```bash
sha256sum -c SHA256SUMS
python3 scripts/ts_decode_score_audit.py inspect --manifest manifest.json
python3 scripts/ts_decode_score_audit.py decode-pair --manifest manifest.json --pair Johnny_QP32_prefix17 --first-poc 0 --last-poc 16 --verify-off --output results/prefix
python3 scripts/ts_decode_score_audit.py batch --manifest manifest.json --pairs all --jobs 4 --first-poc 0 --last-poc 299 --verify-off --output results/full --dry-run
```

先检查dry-run任务清单，再去掉--dry-run；续跑同一请求增加--resume。
all排除validation_only前缀；包未包含前缀时选择manifest中的完整pair。
观察POC不等于解码帧数限制，仍读取全部码流保留参考关系。两来源共享任务池，没有实验组屏障。
方法/原生/单点/快照/输出分别核对；summary不请求回放，部分数据不作0处理。
这些是固定q的条件评分统计，不是BD-rate。CE01缺完整搜索fixture，不能由最终.bin恢复。
本包为本地归档，不意味着已经远程发布；未在其它发行版/glibc/SSE-only机器验收。
''')
        files=sorted(p for p in root.rglob('*') if p.is_file())
        (root/'SHA256SUMS').write_text(''.join(f'{audit.sha(p)}  {p.relative_to(root).as_posix()}\n' for p in files))
        with tarfile.open(args.output,'w:gz',compresslevel=1) as archive:archive.add(root,arcname=root.name)
    digest=audit.sha(args.output)
    args.output.with_name(args.output.name+'.sha256').write_text(f'{digest}  {args.output.name}\n')
    result=dict(archive=str(args.output),sha256=digest,bytes=args.output.stat().st_size,pairs=len(pairs),streams=2*len(pairs),remote_binary_published=False)
    audit.save(args.output.with_name(args.output.name+'.json'),result);print(json.dumps(result,indent=2))


def verify(args):
    if args.output.exists():raise ValueError('Use a new extraction directory')
    expected=args.sha256
    if expected and audit.sha(args.archive)!=expected:raise ValueError('Archive SHA256 mismatch')
    args.output.mkdir(parents=True)
    with tarfile.open(args.archive,'r:gz') as archive:
        members=archive.getmembers()
        if len(members)>3000 or sum(m.size for m in members)>2*1024**3:raise ValueError('Archive exceeds delivery limits')
        for member in members:
            rel=Path(member.name)
            if rel.is_absolute() or '..' in rel.parts or (not member.isdir() and not member.isfile()):raise ValueError('Unsafe archive member')
            destination=args.output/rel
            if member.isdir():destination.mkdir(parents=True,exist_ok=True);continue
            destination.parent.mkdir(parents=True,exist_ok=True)
            with archive.extractfile(member) as src,destination.open('wb') as dst:shutil.copyfileobj(src,dst)
            destination.chmod(member.mode&0o755)
    root=args.output/'r13_decode_audit'
    for line in (root/'SHA256SUMS').read_text().splitlines():
        digest,name=line.split('  ',1);rel=Path(name)
        if rel.is_absolute() or '..' in rel.parts or audit.sha(root/rel)!=digest:raise ValueError('Packaged file checksum mismatch')
    manifest,decoder=audit.inspect_manifest(root/'manifest.json')
    result=dict(archive_sha256=audit.sha(args.archive),checksums_verified=True,
        pairs=len(manifest['pairs']),streams=sum(len(p['origins']) for p in manifest['pairs']),decoder_sha256=audit.sha(decoder),
        relocation_verified=False,independent_OS_validated=False,remote_download_verified=False,smoke_pair=None)
    if args.smoke_pair:
        command=['python3','scripts/ts_decode_score_audit.py','decode-pair','--manifest','manifest.json',
            '--pair',args.smoke_pair,'--first-poc','0','--last-poc','16','--verify-off','--output','relocated_smoke']
        completed=subprocess.run(command,cwd=root,text=True,capture_output=True)
        (root/'relocation_driver.log').write_text(completed.stdout+completed.stderr)
        if completed.returncode:raise ValueError('Relocated paired decode failed: '+completed.stderr)
        result['smoke_pair']=args.smoke_pair
        result['origins']={origin:audit.read_json(root/'relocated_smoke'/origin/'decode_validation.json') for origin in audit.NATIVE}
        if not all(v['audit_complete'] and v['on_off_equal'] for v in result['origins'].values()):raise ValueError('Relocated audit incomplete')
        result['relocation_verified']=True
    audit.save(args.output/'package_validation.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='origins'},indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    b=sub.add_parser('build');b.add_argument('--manifest',type=Path,required=True);b.add_argument('--pairs',default='all');b.add_argument('--output',type=Path,required=True)
    v=sub.add_parser('verify');v.add_argument('--archive',type=Path,required=True);v.add_argument('--sha256');v.add_argument('--output',type=Path,required=True);v.add_argument('--smoke-pair')
    args=p.parse_args();build(args) if args.action=='build' else verify(args)

if __name__=='__main__':main()
