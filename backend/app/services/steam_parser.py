"""Parse developer-published English requirements without inferring target FPS."""
from __future__ import annotations
import re
from bs4 import BeautifulSoup
from app.services.cpu_requirements import CpuRequirementResolver
from app.services.requirements_anchored_fps import resolve_gpu_requirement

VERSION='steam_requirements_v1'
LABELS={'processor':'cpu','graphics':'gpu','os':'os','directx':'directx','additional notes':'notes','memory':'memory','storage':'storage','sound card':'sound','network':'network','vr support':'vr_support'}
LABEL_RE=re.compile(r'(?i)\b(Additional Notes|Sound Card|VR Support|Processor|Graphics|DirectX|Storage|Memory|Network|OS)\s*:')
GPU_RE=re.compile(r'(?i)(?:(?:NVIDIA|AMD|ATI|Intel)\s+)?(?:(?:GeForce|Radeon)\s+)?(?:RTX\s*\d{3,4}|GTX\s*\d{3,4}|GT\s*\d{3,4}|RX\s*\d{3,4}|R[579]\s*\d{3}|HD\s*\d{3,4}|Arc\s*[AB]\d{3})(?:\s*(?:Ti|SUPER|XTX|XT))*(?![a-z0-9])(?:\s*(?:Laptop|Mobile)(?:\s+GPU)?)?(?:\s*\(?\s*\d+\s*(?:GB|MB)(?:\s+VRAM)?\s*\)?)?')

def clean(value):
    soup=BeautifulSoup(str(value or '')[:131072],'html.parser')
    for tag in soup(['script','style']):tag.decompose()
    return ' '.join(soup.get_text(' ',strip=True).replace('\xa0',' ').split())

def split_requirements(raw):
    raw=raw if isinstance(raw,str) else ''
    text=clean(raw);marks=list(LABEL_RE.finditer(text));fields={}
    for i,match in enumerate(marks):
        value=text[match.end():marks[i+1].start() if i+1<len(marks) else len(text)].strip()
        fields[LABELS[match.group(1).casefold()]]=value
    notes=fields.get('notes','')
    fps=set(int(v) for v in re.findall(r'(?i)(?<![\d.])(\d{1,4})\s*FPS\b',notes) if 0<int(v)<=2000)
    resolutions=set(re.findall(r'(?i)\b(720p|1080p|1440p|2160p|4k)\b',notes))
    for width,height in re.findall(r'(?<!\d)(1280|1920|2560|3840)\s*[x×]\s*(720|1080|1440|2160)(?!\d)',notes):
        if (width,height) in (('1280','720'),('1920','1080'),('2560','1440'),('3840','2160')):resolutions.add(height+'p')
    presets=set(v.casefold() for v in re.findall(r'(?i)\b(low|medium|high|ultra|epic)\s+(?:settings|preset)\b',notes))
    vram=sorted({round(float(v)/(1024 if unit.casefold()=='mb' else 1),3) for v,unit in re.findall(r'(?i)(\d+(?:\.\d+)?)\s*(GB|MB)\b',fields.get('gpu',''))})
    rt=False if re.search(r'(?i)(?:no|without)\s+ray tracing|ray tracing\s+(?:off|disabled)',notes) else None
    upscaling='off' if re.search(r'(?i)\bnative rendering\b|(?:no|without)\s+upscaling',notes) else None
    fg=False if re.search(r'(?i)(?:no|without)\s+(?:frame generation|FG)\b|frame generation\s+(?:off|disabled)',notes) else None
    return {'raw_html':str(raw or ''),'text':text,'cpu':fields.get('cpu') or None,'gpu':fields.get('gpu') or None,
        'vram_gb_values':vram,'os':fields.get('os') or None,'directx':fields.get('directx') or None,
        'notes':notes or None,'target_fps':next(iter(fps)) if len(fps)==1 else None,
        'target_resolution':next(iter(resolutions)).casefold() if len(resolutions)==1 else None,
        'target_preset':next(iter(presets)) if len(presets)==1 else None,
        'rt':rt,'upscaling':upscaling,'frame_generation':fg,'fields':fields}

def match_level(level,cpus,gpus):
    cpu_text=level.get('cpu') or ''
    # Explicit mobile context must not resolve to a desktop lookalike.
    if re.search(r'(?i)\b(laptop|mobile|notebook)\b',cpu_text):
        cpus=[c for c in cpus if re.search(r'(?i)\b(laptop|mobile|notebook)\b',c.name)]
    cpu=CpuRequirementResolver(cpus).resolve(cpu_text)
    gpu_text=level.get('gpu') or ''
    tokens=[re.sub(r'\s+',' ',m.group(0)).strip() for m in GPU_RE.finditer(gpu_text)]
    gpu=resolve_gpu_requirement(' or '.join(tokens),gpus)
    # A known SKU may have no trustworthy VRAM field in the legacy catalog.
    # Retain that uncertainty, and never cross a known conflicting VRAM variant.
    if gpu.get('status') != 'resolved_exact_models' and tokens:
        from app.services.hardware_matching import model_key
        vram_re=re.compile(r'(?i)\b(\d+)\s*(GB|MB)(?:\s+VRAM)?\b')
        resolved=[];unresolved=[];unknown_vram=False
        for token in tokens:
            exact=resolve_gpu_requirement(token,gpus)
            if exact.get('status')=='resolved_exact_models':
                resolved.extend(exact['resolved_models']);continue
            base=vram_re.sub('',token).strip(' ()')
            candidates=[g for g in gpus if model_key(vram_re.sub('',g.name))==model_key(base)]
            explicit=[g for g in candidates if vram_re.search(g.name)]
            required=vram_re.search(token)
            if required and candidates and not explicit:
                fallback=resolve_gpu_requirement(base,candidates)
                if fallback.get('status')=='resolved_exact_models':
                    for model in fallback['resolved_models']:model['vram_validation']='unknown_in_catalog'
                    resolved.extend(fallback['resolved_models']);unknown_vram=True;continue
            unresolved.extend(exact.get('unresolved_models') or [{'token':token,'reason':'unmatched_variant'}])
        if resolved:
            scores=[m['g3d_mark'] for m in resolved]
            from statistics import median
            gpu={**gpu,'status':'partially_resolved' if unresolved else 'resolved_exact_models',
                 'resolved_models':resolved,'unresolved_models':unresolved,
                 'reference_gpu_mark':median(scores),'reference_gpu_mark_range':[min(scores),max(scores)],
                 'vram_validation':'partly_unknown' if unknown_vram else 'explicit',
                 'match_confidence':'medium' if unknown_vram else 'high'}

    if gpu_text and not tokens:
        gpu={'status':'unmatched','resolved_models':[],'unresolved_models':[{'token':gpu_text,'reason':'no_exact_gpu_model'}]}
    return {**level,'cpu_match':cpu,'gpu_match':gpu,'gpu_alternatives':tokens,
            'fully_resolved':cpu.get('status')==gpu.get('status')=='resolved_exact_models'}

def parse_requirements(data,cpus=(),gpus=()):
    raw=data.get('pc_requirements')
    raw=raw if isinstance(raw,dict) else {}
    levels={kind:match_level(split_requirements(raw.get(kind,'')),list(cpus),list(gpus)) for kind in ('minimum','recommended')}
    recommended=levels['recommended']
    return {**levels,'parser_version':VERSION,'source_type':'developer_published_requirements',
        'parsing_status':'resolved' if recommended['fully_resolved'] else 'partial' if recommended['text'] else 'recommended_absent',
        'match_confidence':'high' if recommended['fully_resolved'] else 'partial' if recommended['text'] else 'none',
        'official_target':({'fps':recommended['target_fps'],'resolution':recommended['target_resolution'],
            'preset':recommended['target_preset'],'rt':recommended['rt'],'upscaling':recommended['upscaling'],'frame_generation':recommended['frame_generation'],
            'source_type':'developer_stated_target_not_measurement'} if recommended['target_fps'] is not None else None)}
