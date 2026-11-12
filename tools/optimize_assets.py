"""Development asset pipeline; Pillow is not a backend runtime dependency."""
import argparse,json,hashlib
from pathlib import Path
from PIL import Image,ImageOps

def run(source,destination):
 source=Path(source);destination=Path(destination);destination.mkdir(parents=True,exist_ok=True);report=[]
 for file in sorted(source.glob('*.png')):
  with Image.open(file) as raw:
   original=ImageOps.exif_transpose(raw).convert('RGB')
   widths=[1536,1200,800] if file.stem=='hero' else [800,480,320] if file.stem=='hero_mobile' else [480,320,160]
   for width in widths:
    if width>original.width:continue
    image=original.resize((width,round(original.height*width/original.width)),Image.Resampling.LANCZOS)
    path=destination/f'{file.stem}-{width}.webp';image.save(path,'WEBP',quality=83,method=6)
    with Image.open(path) as check:check.verify()
    report.append({'asset':file.stem,'file':path.name,'width':image.width,'height':image.height,'bytes':path.stat().st_size,'original_bytes':file.stat().st_size,'source_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'saved_percent':round((1-path.stat().st_size/file.stat().st_size)*100,2),'origin':'Original generated illustration; not a SKU photograph','tool':'built-in image_gen','created_at':'2026-11-10'})
 (destination/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');return report
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True);args=p.parse_args();r=run(args.source,args.output);print(json.dumps({'files':len(r),'bytes':sum(x['bytes'] for x in r),'max_bytes':max(x['bytes'] for x in r)}))
