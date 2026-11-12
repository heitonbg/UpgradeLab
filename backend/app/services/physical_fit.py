"""Conservative physical constraints; missing dimensions are not compatibility."""
import json

def physical_fit(board,gpu,case,supply,cooler):
    parts=(board,gpu,case,supply,cooler)
    if any(p is None for p in parts):return {'status':'unknown','reason':'physical_dimensions_missing'}
    def attrs(row):
        try:return json.loads(row.attributes)
        except (ValueError,AttributeError):return {}
    b,g,c,p,k=map(attrs,parts);missing=[]
    for supported,actual,reason in ((c.get('board_formats'),b.get('form_factor'),'case_board_format'),(c.get('psu_formats'),p.get('form_factor'),'case_psu_format')):
        if supported and actual:
            if actual not in supported:return {'status':'incompatible','reason':reason}
        else:missing.append(reason)
    for maximum,size,reason in ((c.get('max_gpu_length_mm'),g.get('length_mm'),'case_gpu_length'),(c.get('max_cooler_height_mm'),k.get('height_mm'),'case_cooler_height')):
        if type(maximum) is int and type(size) is int:
            if size>maximum:return {'status':'incompatible','reason':reason}
        else:missing.append(reason)
    if missing:return {'status':'unknown','reason':'physical_dimensions_missing','missing':missing}
    seller=any(getattr(part,'source',None)=='upgradelab' for part in parts)
    return {'status':'unknown' if seller else 'compatible','reason':'seller_declared_dimensions' if seller else 'documented_dimensions'}
