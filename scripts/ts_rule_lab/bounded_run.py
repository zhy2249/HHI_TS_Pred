#!/usr/bin/env python3
"""Run one experiment stage with Linux process-memory bounds and a receipt.

Does not change codec/scoring code or resume identities. Cache hints apply only
to derived .pred/.partial/.jsonl.gz files under the explicitly supplied root.
Start with --jobs 1 in the wrapped command, and keep stages sequential. This
wrapper never schedules extra work; its RSS threshold covers all child workers.
"""
import argparse, fcntl, json, os, resource, signal, subprocess, sys, time
from pathlib import Path


def tree_rss(root):
    stats={}
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():continue
        try:
            fields={k:v.strip() for k,v in (x.split(':',1) for x in (path/'status').read_text().splitlines() if ':' in x)}
            stats[int(path.name)]=(int(fields['PPid']),int(fields.get('VmRSS','0 kB').split()[0])*1024)
        except (OSError,ValueError,KeyError):continue
    selected={root}
    while True:
        more={pid for pid,(parent,_) in stats.items() if parent in selected}-selected
        if not more:break
        selected.update(more)
    return sum(stats.get(pid,(0,0))[1] for pid in selected)


def release_cache(root):
    if root is None or not hasattr(os,'posix_fadvise'):return 0
    count=0
    for path in root.rglob('*'):
        if not path.is_file() or path.is_symlink() or not path.name.endswith(('.pred','.partial','.jsonl.gz')):continue
        try:
            if path.stat().st_size<16*1024**2:continue
            fd=os.open(path,os.O_RDONLY)
            try:
                os.fdatasync(fd)
                os.posix_fadvise(fd,0,0,os.POSIX_FADV_DONTNEED)
                count+=1
            finally:os.close(fd)
        except OSError:continue
    return count


def run(args):
    args.receipt.parent.mkdir(parents=True,exist_ok=True)
    # An interrupted launcher can outlive its terminal. Serialize the task root
    # across stages (or the receipt if no task root was supplied).
    lock_path=args.receipt.with_suffix(args.receipt.suffix+'.lock')
    if args.cache_root is not None:
        args.cache_root.mkdir(parents=True,exist_ok=True)
        lock_path=args.cache_root/'.bounded_run.lock'
    with lock_path.open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('This task root/receipt already has an active runner')
        return run_owned(args)


def run_owned(args):
    command=args.command[1:] if args.command[:1]==['--'] else args.command
    if not command:raise ValueError('A command is required after --')
    if args.cache_seconds<=0:raise ValueError('Positive cache interval required')
    if args.receipt.exists():raise ValueError('Use a new receipt path')
    args.receipt.parent.mkdir(parents=True,exist_ok=True)
    as_limit=args.as_limit_mib*1024**2;rss_limit=args.rss_limit_mib*1024**2
    if not 0<rss_limit<=as_limit:raise ValueError('Require 0 < RSS limit <= address-space limit')
    def limits():
        resource.setrlimit(resource.RLIMIT_AS,(as_limit,as_limit))
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    env=os.environ.copy();env['MALLOC_ARENA_MAX']='2'
    hints=release_cache(args.cache_root);start=time.monotonic()
    proc=subprocess.Popen(command,env=env,start_new_session=True,preexec_fn=limits)
    peak=0;reason=None;last_hint=start
    try:
        while proc.poll() is None:
            rss=tree_rss(proc.pid);peak=max(peak,rss)
            if rss>rss_limit:
                reason='process_tree_RSS_limit';os.killpg(proc.pid,signal.SIGTERM)
                try:proc.wait(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL)
                break
            if time.monotonic()-last_hint>=args.cache_seconds:
                hints+=release_cache(args.cache_root);last_hint=time.monotonic()
            time.sleep(1)
    except BaseException:
        if proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM)
        raise
    finally:
        rc=proc.wait();hints+=release_cache(args.cache_root)
        result=dict(command=command,returncode=rc,stop_reason=reason,
            address_space_limit_bytes_per_process=as_limit,process_tree_RSS_limit_bytes=rss_limit,
            sampled_peak_tree_RSS_bytes=peak,sampling_seconds=1,file_cache_hints=hints,
            cache_hint_interval_seconds=args.cache_seconds,
            cache_root=str(args.cache_root) if args.cache_root else None,
            cache_hint='fdatasync + POSIX_FADV_DONTNEED, task derived files only; advisory',
            elapsed_seconds=time.monotonic()-start)
        args.receipt.write_text(json.dumps(result,indent=2)+'\n')
    return rc if rc>=0 else 128-rc


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--as-limit-mib',type=int,default=3072);p.add_argument('--rss-limit-mib',type=int,default=2048)
    p.add_argument('--cache-root',type=Path);p.add_argument('--receipt',type=Path,required=True)
    p.add_argument('--cache-seconds',type=float,default=5)
    p.add_argument('command',nargs=argparse.REMAINDER);sys.exit(run(p.parse_args()))
