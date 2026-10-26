#!/usr/bin/env python3
"""Opt-in corpus integration. Default is dry-run; no build or encoder launch.

Only writes two tracked files plus a new Corpus.h when --apply is explicit.
Dirty target files, unsupported source anchors, or an existing Corpus.h stop
this script. Reconcile those cases manually; never override user changes.
"""
from pathlib import Path
import argparse,hashlib,subprocess

BASE='6beb4504f0aae7f1895f819743a7ad5d3efef01a'


def one(s,old,new):
    if s.count(old)!=1:raise ValueError(f'Expected exactly one source anchor: {old[:100]!r}')
    return s.replace(old,new,1)


def transform_manager(s):
    s=one(s,'#include "Replay.h"','#include "Replay.h"\n#include "Corpus.h"')
    s=one(s,'const int v=std::abs(q[i]); pop.nz+=v!=0;',
            'const int v=std::abs(q[geom.blockPos(i)]); pop.nz+=v!=0;')
    old='inline Native *begin(const TransformUnit &tu,CompID c,const Ctx &ctx) { return enabled()?manager().begin(tu,c,ctx):nullptr; }'
    new='inline Native *begin(const TransformUnit &tu,CompID c,const Ctx &ctx) { if(TsCorpus::enabled()) return TsCorpus::begin(tu,c,ctx); return enabled()?manager().begin(tu,c,ctx):nullptr; }'
    s=one(s,old,new)
    s=one(s,'inline void end(const TransformUnit &tu,CompID c,const Ctx &ctx) { if(enabled()) { manager().end(tu,c,ctx); } }',
      'inline void end(const TransformUnit &tu,CompID c,const Ctx &ctx) { if(TsCorpus::enabled()) { TsCorpus::end(tu,c,ctx); return; } if(enabled()) { manager().end(tu,c,ctx); } }')
    s=one(s,'inline void finish(bool success)\n{\n',
      'inline void finish(bool success)\n{\n  if(TsCorpus::enabled()) { TsCorpus::finish(success); return; }\n')
    s=one(s,'if(enabled()) { CHECK(pic.m_layerId!=0,"Audit supports only single-layer streams"); }',
      'if(enabled() || TsCorpus::enabled()) { CHECK(pic.m_layerId!=0,"Audit/corpus supports only single-layer streams"); }')
    return s


def transform_main(s):
    old='  if(argc==2 && std::string(argv[1])=="--ts-audit-version")'
    new='  if(argc==2 && std::string(argv[1])=="--ts-corpus-version")\n  { std::cout<<TsCorpus::revision<<"\\n"; return 0; }\n'+old
    return one(s,old,new)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=Path,required=True)
    p.add_argument('--apply',action='store_true');a=p.parse_args();root=a.repo.resolve()
    rels=['source/Lib/DecoderLib/tsaudit/Manager.h','source/App/DecoderApp/decmain.cpp']
    dirty=subprocess.check_output(['git','status','--porcelain','--',*rels],cwd=root,text=True)
    if dirty:raise ValueError('Affected source files have user edits; reconcile first:\n'+dirty)
    ancestor=subprocess.run(['git','merge-base','--is-ancestor',BASE,'HEAD'],cwd=root)
    if ancestor.returncode:raise ValueError('Expected audited baseline is not an ancestor of HEAD')
    dst='source/Lib/DecoderLib/tsaudit/Corpus.h'
    if (root/dst).exists():raise ValueError('Corpus.h already exists; do not overwrite it')
    changes={rels[0]:transform_manager((root/rels[0]).read_text()),
             rels[1]:transform_main((root/rels[1]).read_text()),
             dst:(Path(__file__).resolve().parent/'native/Corpus.h').read_text()}
    for name,body in changes.items():
        print(name,len(body.encode()),hashlib.sha256(body.encode()).hexdigest())
        if a.apply:(root/name).write_text(body)
    print('APPLIED; run native tests and rebuild DecoderApp.' if a.apply else 'DRY RUN; no files modified. Add --apply to write.')


if __name__=='__main__':main()
